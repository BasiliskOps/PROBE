"""Intent agent: one sentence in, a mission spec the trajectory engine can fly."""
from __future__ import annotations

import re

from app.astro.constants import MOONS, PLANETS
from app.config import settings

from .llm import obj, structured

TARGETS = [p for p in PLANETS if p != "earth"] + list(MOONS)
CLASSES = {"small": 600.0, "medium": 1800.0, "flagship": 3200.0}

TOOL = {
    "name": "mission_intent",
    "description": "Record what the owner asked this probe to do.",
    "input_schema": obj(
        {
            "supported": {"type": "boolean", "description": "False if the destination is not in the target list."},
            "unsupported_reason": {"type": "string"},
            "target": {"type": "string", "enum": TARGETS},
            "arrival": {"type": "string", "enum": ["orbit", "flyby"],
                        "description": "orbit unless the owner only wants to pass by"},
            "via": {"type": "array", "items": {"type": "string", "enum": [p for p in PLANETS if p != "earth"]},
                    "description": "Planets the owner explicitly wants to pass on the way"},
            "photograph": {"type": "array", "items": {"type": "string"},
                           "description": "Bodies the owner wants imaged"},
            "probe_class": {"type": "string", "enum": list(CLASSES)},
            "probe_name": {"type": "string", "description": "Name the owner gave the probe, if any"},
            "priority": {"type": "string", "enum": ["soonest", "fastest", "heaviest"],
                         "description": "soonest unless the owner asks for speed or a big probe"},
            "objective": {"type": "string", "description": "The owner's goal in one plain sentence"},
        },
        ["supported", "target", "arrival", "via", "probe_class", "priority", "objective"],
    ),
}

SYSTEM = (
    "You turn a one-sentence space mission request into a structured intent for a trajectory engine. "
    "Supported destinations are the planets Mercury through Neptune and the moons Io, Europa, Ganymede, "
    "Callisto, Titan, Enceladus, Triton and Phobos. Asteroids, comets, dwarf planets, the Sun and the Moon "
    "are not supported yet; mark those unsupported and say why in one sentence. 'On the way' bodies go in via "
    "only when they are planets. Use probe_class medium unless the request implies a tiny or a flagship probe."
)


def _fallback(sentence: str) -> dict:
    s = sentence.lower()
    hits = [(s.find(t), t) for t in TARGETS if re.search(rf"\b{t}\b", s)]
    if not hits:
        return {"supported": False, "unsupported_reason": "No supported destination named.", "target": "jupiter",
                "arrival": "orbit", "via": [], "photograph": [], "probe_class": "medium", "priority": "soonest",
                "objective": sentence}
    named = [t for _, t in sorted(hits)]
    aimed = re.search(rf"\b(?:to|past|around|orbit|at|reach)\s+(?:the\s+)?(?:moon\s+|planet\s+)?({'|'.join(TARGETS)})\b", s)
    if any(t in MOONS for t in named):
        target = next(t for t in named if t in MOONS)
    elif aimed:
        target = aimed.group(1)
    else:  # the destination is usually the farthest body named
        from app.astro.constants import BODY

        target = max(named, key=lambda t: BODY[t]["a_au"])
    planet = MOONS[target]["parent"] if target in MOONS else target
    via = [t for _, t in sorted(hits) if t in PLANETS and t not in (target, planet)]
    arrival = "flyby" if re.search(r"\bfly ?by\b|\bflies past\b|\bpass(es)? (by )?\b", s) and not re.search(
        r"\borbit\b", s) else "orbit"
    return {"supported": True, "target": target, "arrival": arrival, "via": via,
            "photograph": [t for _, t in sorted(hits)], "probe_class": "medium", "priority": "soonest",
            "objective": sentence}


async def parse(sentence: str) -> dict:
    out = await structured(settings.model_agents, SYSTEM, f"Mission request: {sentence}", TOOL, 800)
    intent = out if out else _fallback(sentence)
    intent.setdefault("via", [])
    intent.setdefault("photograph", [])
    intent["source"] = "model" if out else "rules"
    return intent
