"""Intent agent: one sentence in, a mission spec the engine can fly.

Two kinds of mission: prospecting an asteroid (the core of PROBE) and
visiting a planet or moon.
"""
from __future__ import annotations

import re

from app.astro.constants import MOONS, PLANETS
from app.config import settings

from .llm import obj, structured

TARGETS = [p for p in PLANETS if p != "earth"] + list(MOONS)
CLASSES = {"small": 600.0, "medium": 1800.0, "flagship": 3200.0}
RESOURCE_WORDS = {
    "water": ["water", "ice", "volatile", "hydrat", "propellant", "fuel", "hydrogen", "oxygen", "gas"],
    "pgm": ["platinum", "palladium", "iridium", "rhodium", "osmium", "ruthenium", "pgm", "precious"],
    "nickel": ["nickel"],
    "cobalt": ["cobalt"],
    "iron": ["iron", "steel", "metal", "metallic", "ore"],
    "carbon": ["carbon", "organic", "carbonaceous"],
}
RESOURCES = list(RESOURCE_WORDS) + ["any"]

TOOL = {
    "name": "mission_intent",
    "description": "Record what the owner asked this probe to do.",
    "input_schema": obj(
        {
            "supported": {"type": "boolean", "description": "False only for comets, the Sun, the Moon or places outside the solar system."},
            "unsupported_reason": {"type": "string"},
            "kind": {"type": "string", "enum": ["asteroid", "planet"],
                     "description": "asteroid for prospecting or any named asteroid; planet for planets and moons"},
            "resource": {"type": "string", "enum": RESOURCES,
                         "description": "What the owner is prospecting for. Gases and propellant map to water."},
            "asteroid": {"type": "string", "description": "Asteroid name or designation if the owner named one, e.g. Bennu, 16 Psyche, 2024 YR4"},
            "region": {"type": "string", "enum": ["near-earth", "main-belt", "any"]},
            "target": {"type": "string", "enum": TARGETS, "description": "For kind=planet only"},
            "arrival": {"type": "string", "enum": ["orbit", "flyby"],
                        "description": "orbit means rendezvous for asteroids; flyby only if the owner wants a pass"},
            "via": {"type": "array", "items": {"type": "string", "enum": [p for p in PLANETS if p != "earth"]}},
            "probe_class": {"type": "string", "enum": list(CLASSES)},
            "probe_name": {"type": "string"},
            "priority": {"type": "string", "enum": ["soonest", "fastest", "heaviest"]},
            "objective": {"type": "string", "description": "The owner's goal in one plain sentence"},
        },
        ["supported", "kind", "resource", "region", "arrival", "via", "probe_class", "priority", "objective"],
    ),
}

SYSTEM = (
    "You turn a one-sentence space mission request into a structured intent. PROBE prospects asteroids for "
    "critical resources: water and volatiles (the source of propellant gases), iron, nickel, cobalt, carbon and "
    "platinum-group metals. Any request about mining, prospecting, resources, minerals, gases or a named asteroid "
    "is kind=asteroid. Requests for planets or the moons Io, Europa, Ganymede, Callisto, Titan, Enceladus, Triton "
    "or Phobos are kind=planet. Use region near-earth unless the owner names the main belt or a main-belt body. "
    "Use probe_class small for prospectors unless the owner implies a large probe."
)


def _resource(s: str) -> str:
    for res, words in RESOURCE_WORDS.items():
        if any(w in s for w in words):
            return res
    return "any"


def _fallback(sentence: str) -> dict:
    from app.prospect import catalog

    s = sentence.lower()
    if re.search(r"\bcomet|\bthe sun\b|\bthe moon\b|\blunar\b|exoplanet|another star", s):
        return {"supported": False, "unsupported_reason": "Comets, the Sun and the Moon are not supported yet. "
                "PROBE flies to asteroids, planets and the major moons of the outer planets.",
                "kind": "asteroid", "resource": "any", "region": "any", "arrival": "orbit", "via": [],
                "probe_class": "small", "priority": "soonest", "objective": sentence}
    base = {"supported": True, "via": [], "probe_class": "small", "priority": "soonest", "objective": sentence,
            "region": "main-belt" if "main belt" in s or "main-belt" in s else "near-earth"}
    named = None
    for tok in re.findall(r"\d{4} [a-z]{1,2}\d*|\d+|[a-z]{3,}", s):
        if tok in TARGETS or tok in ("probe", "asteroid", "send", "find", "the", "and", "for"):
            continue
        named = catalog.find(tok)
        if named:
            break
    hits = [(s.find(t), t) for t in TARGETS if re.search(rf"\b{t}\b", s)]
    asteroid_words = named or re.search(r"asteroid|prospect|mine|mining|mineral|resource|ore|gas|metal", s)
    if asteroid_words or not hits:
        arrival = "flyby" if re.search(r"\bfly ?by\b|\bflies past\b|\bpass(es)? by\b", s) else "orbit"
        return {**base, "kind": "asteroid", "resource": _resource(s), "asteroid": named["name"] if named else None,
                "arrival": arrival, "target": None}
    named_p = [t for _, t in sorted(hits)]
    aimed = re.search(rf"\b(?:to|past|around|orbit|at|reach)\s+(?:the\s+)?(?:moon\s+|planet\s+)?({'|'.join(TARGETS)})\b", s)
    if any(t in MOONS for t in named_p):
        target = next(t for t in named_p if t in MOONS)
    elif aimed:
        target = aimed.group(1)
    else:
        from app.astro.constants import BODY

        target = max(named_p, key=lambda t: BODY[t]["a_au"])
    planet = MOONS[target]["parent"] if target in MOONS else target
    via = [t for t in named_p if t in PLANETS and t not in (target, planet)]
    arrival = "flyby" if re.search(r"\bfly ?by\b|\bflies past\b|\bpass(es)? (by )?\b", s) and not re.search(
        r"\borbit\b", s) else "orbit"
    return {**base, "kind": "planet", "resource": "any", "target": target, "arrival": arrival, "via": via,
            "probe_class": "medium"}


async def parse(sentence: str) -> dict:
    out = await structured(settings.model_agents, SYSTEM, f"Mission request: {sentence}", TOOL, 800)
    intent = out if out else _fallback(sentence)
    intent.setdefault("via", [])
    intent.setdefault("resource", "any")
    intent.setdefault("region", "near-earth")
    intent["source"] = "model" if out else "rules"
    return intent
