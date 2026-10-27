"""The probe's crew: a persona agent that gives it a character, a flight director that
writes the mission brief, and a voice agent that writes each milestone message.

Every agent works only from facts the engine computed. Each has a deterministic
fallback so the product keeps flying without a model.
"""
from __future__ import annotations

import json

from app.config import settings

from .llm import obj, structured

STYLE = (
    "Write plain, specific sentences with varied length. Use only the facts and numbers you are given, and "
    "never invent spacecraft hardware, people or events. No emojis, hashtags, exclamation marks or "
    "rhetorical questions. Never use the construction 'not X but Y' or 'it's not A, it's B'. No stock openers "
    "such as 'Imagine', 'In a world', 'Buckle up' or 'Here's the thing', and no closing one-liners."
)

PERSONA_TOOL = {
    "name": "probe_persona",
    "description": "Define the probe's character.",
    "input_schema": obj({
        "name": {"type": "string", "description": "Short probe name; keep the owner's name if they gave one"},
        "personality": {"type": "string", "description": "Two sentences on how this probe thinks and talks"},
        "voice_rules": {"type": "array", "items": {"type": "string"}, "description": "Three concrete voice habits"},
        "launch_message": {"type": "string", "description": "First message to the owner, under 600 characters"},
    }, ["name", "personality", "voice_rules", "launch_message"]),
}

BRIEF_TOOL = {
    "name": "mission_brief",
    "description": "Write the flight director's mission brief.",
    "input_schema": obj({
        "mission_name": {"type": "string"},
        "brief": {"type": "string", "description": "Three to five sentences: route, dates, rocket, why this window"},
    }, ["mission_name", "brief"]),
}

MESSAGE_TOOL = {
    "name": "probe_message",
    "description": "The probe's message to its owner for this milestone.",
    "input_schema": obj({"text": {"type": "string", "description": "Under 700 characters, in character"}}, ["text"]),
}


def human(jd: float) -> str:
    from app.astro.search import dt_from_jd

    d = dt_from_jd(jd)
    return f"{d:%B} {d.day}, {d.year}"


def summarize(m: dict) -> dict:
    """Compact, model-safe facts about a designed mission."""
    from app.astro.search import iso

    from app.missions.flight import body_label

    det, bud = m["detail"], m["budget"]
    sb = m["spec"].get("small_body")
    out = {
        "owner_request": m["sentence"],
        "target": sb["name"] if sb else m["spec"]["target"],
        "arrival": ("rendezvous" if m["spec"]["arrival"] == "orbit" else "flyby") if sb else m["spec"]["arrival"],
        "route": [body_label(b) for b in det["sequence"]],
        "launch_date": iso(det["launch_jd"]),
        "arrival_date": iso(det["arrival_jd"]),
        "flight_years": round((det["arrival_jd"] - det["launch_jd"]) / 365.25, 2),
        "launch_vehicle": m["vehicle"]["name"],
        "c3_km2s2": round(det["c3_km2s2"], 1),
        "flybys": [{"body": f["body"], "date": iso(f["jd"]), "altitude_km": round(f["altitude_km"])}
                   for f in det["flybys"]],
        "deep_space_maneuvers_ms": [round(d["dv_kms"] * 1000) for d in det["dsms"] if d["dv_kms"] > 0.005],
        "arrival_burn_ms": round(det["arrival_dv_kms"] * 1000),
        "probe_dry_mass_kg": round(bud["dry_mass_kg"]),
        "launch_mass_kg": round(bud["wet_mass_kg"]),
        "ephemeris": m["design"]["ephemeris"]["source"],
        "mission_clock": f"{m.get('clock', {}).get('rate', 1):g} mission days pass per real day",
    }
    if sb:
        p = m.get("prior", {})
        out["asteroid"] = {
            "spectral_class": sb.get("spectral_class"), "composition_group": p.get("group"),
            "diameter_km": round(sb["diameter_km"], 3), "near_earth": sb.get("neo"),
            "expected_tonnes_before_survey": {k: float(f"{v:.2g}") for k, v in p.get("tonnes", {}).items()},
            "prospecting_for": m.get("resource"),
        }
    return out


async def persona(m: dict, intent: dict) -> dict:
    facts = summarize(m)
    prompt = ("Create the character of this probe. It is a real-physics probe flying a real trajectory in real "
              "time, and it writes to its owner at milestones for years. Give it a distinct temperament that fits "
              f"the mission. Owner-given name: {intent.get('probe_name') or 'none'}.\nFacts: {json.dumps(facts)}")
    out = await structured(settings.model_agents, "You design characters for robotic space probes. " + STYLE,
                           prompt, PERSONA_TOOL, 1200)
    if out:
        out["source"] = "model"
        return out
    stem = "Prospector" if m["spec"].get("small_body") else facts["target"].title()
    name = intent.get("probe_name") or f"{stem} {m['id'][:4].upper()}"
    return {
        "name": name,
        "personality": "Methodical and dry. It reports what it measures and keeps count of every meter per second.",
        "voice_rules": ["Leads with the number that matters", "Speaks in first person", "Signs off with its name"],
        "launch_message": (f"{name} here. I launch on {human(m['detail']['launch_jd'])} aboard "
                           f"{facts['launch_vehicle']} and reach {facts['target']} on "
                           f"{human(m['detail']['arrival_jd'])}, "
                           f"{facts['flight_years']} years from liftoff. I will write at every milestone."),
        "source": "rules",
    }


async def brief(m: dict) -> dict:
    facts = summarize(m)
    alts = m.get("alternatives", [])
    prompt = (f"Write the mission brief for the owner. Chosen design: {json.dumps(facts)}\n"
              f"Other windows considered: {json.dumps(alts)}")
    out = await structured(settings.model_agents, "You are the flight director of a deep-space mission. " + STYLE,
                           prompt, BRIEF_TOOL, 900)
    if out:
        out["source"] = "model"
        return out
    route = " to ".join(facts["route"])
    fb = "; ".join(f"{f['body'].title()} on {human(x['jd'])} at {f['altitude_km']:,} km"
                   for f, x in zip(facts["flybys"], m["detail"]["flybys"]))
    text = (f"Route: {route}. Launch {human(m['detail']['launch_jd'])} on {facts['launch_vehicle']} at C3 "
            f"{facts['c3_km2s2']} km²/s², arriving {human(m['detail']['arrival_jd'])}.")
    if fb:
        text += f" Gravity assists: {fb}."
    text += f" Launch mass {facts['launch_mass_kg']:,} kg."
    return {"mission_name": f"{facts['target']} {facts['launch_date'][:4]}", "brief": text, "source": "rules"}


def fmt_tonnes(t: float) -> str:
    """3.2 million t, 41,000 t, 380 kg."""
    if t >= 1e9:
        return f"{t / 1e9:.2g} billion t"
    if t >= 1e6:
        return f"{t / 1e6:.2g} million t"
    if t >= 1:
        return f"{float(f'{t:.2g}'):,.0f} t"
    return f"{float(f'{t * 1000:.2g}'):,.0f} kg"


def findings_facts(survey: dict) -> dict:
    from app.prospect.composition import LABELS

    return {"survey_mode": survey["mode"], "composition_group": survey["group"],
            "measured_diameter_km": round(survey["diameter_km"], 3),
            "one_sigma_uncertainty_percent": round(survey["sigma"] * 100),
            "resources": {LABELS[k]: fmt_tonnes(v) for k, v in survey["tonnes"].items()}}


async def milestone_message(m: dict, event: dict, snapshot: dict, decision: dict | None,
                            recent: list[str], use_model: bool = True, survey: dict | None = None) -> str:
    from app.astro.search import iso

    p = m.get("persona", {})
    facts = {"event": event["title"], "date": iso(event["jd"]), "details": event.get("data", {}),
             "now": snapshot, "mission": summarize(m)}
    if survey:
        facts["findings"] = findings_facts(survey)
    if decision:
        facts["decision"] = {"question": decision["question"], "deadline": iso(decision["deadline_jd"]),
                             "options": [{"label": o["label"], "propellant_ms": o["dv_ms"]} for o in decision["options"]]}
    if use_model:
        system = (f"You are {p.get('name', 'the probe')}, a robotic space probe writing to your owner. "
                  f"Personality: {p.get('personality', '')} Voice: {'; '.join(p.get('voice_rules', []))}. " + STYLE)
        prompt = (f"Write your message for this milestone. If there is a decision, ask the owner to choose "
                  f"and state each option's propellant cost. If there are findings, report what you measured, "
                  f"lead with what the owner was prospecting for, and give the uncertainty. "
                  f"Your last messages: {json.dumps(recent[-3:])}\n"
                  f"Facts: {json.dumps(facts)}")
        out = await structured(settings.model_voice, system, prompt, MESSAGE_TOOL, 600)
        if out and out.get("text"):
            return out["text"].strip()
    name = p.get("name", "Probe")
    line = f"{event['title']}, {human(event['jd'])}."
    d = event.get("data", {})
    if "altitude_km" in d:
        line += f" Closest approach {d['altitude_km']:,} km."
    if "dv_ms" in d:
        line += f" Burn {d['dv_ms']} m/s."
    line += f" I am {snapshot['earth_distance_au']:.2f} AU from Earth; light takes {snapshot['light_time_min']:.1f} min."
    if survey:
        ff = findings_facts(survey)
        res = ", ".join(f"{k.lower()} {v}" for k, v in ff["resources"].items())
        line += (f" Measured diameter {ff['measured_diameter_km'] * 1000:,.0f} m, {ff['composition_group']} body. "
                 f"Estimated {res}, each within about {ff['one_sigma_uncertainty_percent']}%.")
    if decision:
        opts = "; ".join(f"{o['label']} ({o['dv_ms']} m/s)" for o in decision["options"])
        line += f" {decision['question']} Options: {opts}. Decide by {human(decision['deadline_jd'])}."
    return f"{line} {name}"
