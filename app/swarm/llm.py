"""Thin Claude client: one forced tool call per agent turn, returning structured JSON."""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

_client = None


def client():
    """AsyncAnthropic client, or None when no API key is configured."""
    global _client
    if not settings.anthropic_api_key:
        return None
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def set_client(c) -> None:
    """Inject a client (tests)."""
    global _client
    _client = c


async def structured(model: str, system: str, prompt: str, tool: dict, max_tokens: int = 2000) -> dict | None:
    """Ask the model to answer by calling `tool`; returns the tool input, or None if unavailable."""
    c = _client or client()
    if c is None:
        return None
    try:
        resp = await c.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
        )
    except Exception as exc:
        log.warning("model call failed (%s): %s", tool["name"], exc)
        return None
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
            return dict(block.input)
    return None


def obj(properties: dict[str, Any], required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}
