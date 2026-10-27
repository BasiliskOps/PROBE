"""Agent layer with a stand-in Claude client: forced tool calls are parsed and used."""
import asyncio
from types import SimpleNamespace

from app.swarm import intent, llm


class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    async def create(self, **kw):
        self.calls.append(kw)
        name = kw["tool_choice"]["name"]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name=name, input=self.replies[name])])


def test_intent_uses_model_tool_call():
    fake = FakeMessages({"mission_intent": {
        "supported": True, "target": "titan", "arrival": "orbit", "via": ["jupiter"], "photograph": ["jupiter"],
        "probe_class": "flagship", "priority": "soonest", "objective": "Titan via Jupiter", "probe_name": "Huygens II"}})
    llm.set_client(SimpleNamespace(messages=fake))
    try:
        out = asyncio.run(intent.parse("Send Huygens II to Titan and grab Jupiter on the way"))
    finally:
        llm.set_client(None)
    assert out["source"] == "model" and out["target"] == "titan" and out["via"] == ["jupiter"]
    call = fake.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "mission_intent"}
    assert call["tools"][0]["input_schema"]["properties"]["target"]["enum"]


def test_model_failure_falls_back_to_rules():
    class Boom:
        async def create(self, **kw):
            raise RuntimeError("overloaded")

    llm.set_client(SimpleNamespace(messages=Boom()))
    try:
        out = asyncio.run(intent.parse("Put a probe in orbit around Saturn"))
    finally:
        llm.set_client(None)
    assert out["source"] == "rules" and out["target"] == "saturn"
