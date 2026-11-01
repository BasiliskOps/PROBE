"""Rank resource-bearing bodies from published catalog data.

Deterministic: the same catalog in gives the same ranking out. Expected
tonnage comes from composition.prior (spectral class or albedo mapped to
meteorite analogs); the low and high bounds use the analog ranges for that
group. Reach is planner.reach_dv_kms, a rough rendezvous cost from Earth's
orbit used for ordering only. No language model touches any number here.
"""
from __future__ import annotations

import math

from . import composition, planner

RESOURCES = composition.RESOURCES


def _bounds(target: dict, group: str, mass: float) -> dict:
    g = composition.GROUPS[group]
    m = composition.METAL
    lo = composition._tonnes({"water": g["water"][0], "carbon": g["carbon"][0], "metal": g["metal"][0],
                              "nickel": m["nickel"][0], "cobalt": m["cobalt"][0], "pgm": m["pgm"][0]}, mass)
    hi = composition._tonnes({"water": g["water"][1], "carbon": g["carbon"][1], "metal": g["metal"][1],
                              "nickel": m["nickel"][1], "cobalt": m["cobalt"][1], "pgm": m["pgm"][1]}, mass)
    return {k: (lo[k], hi[k]) for k in lo}


def score(tonnes: float, dv: float) -> float:
    return math.log10(max(tonnes, 1.0)) - 1.2 * dv


def assess(target: dict) -> dict:
    p = composition.prior(target)
    dv = planner.reach_dv_kms(target)
    bounds = _bounds(target, p["group"], p["mass_kg"])
    total = sum(p["tonnes"].values())
    scores = {k: score(v, dv) for k, v in p["tonnes"].items()}
    scores["any"] = score(total, dv)
    return {"group": p["group"], "basis": p["basis"], "mass_kg": p["mass_kg"], "dv": dv,
            "tonnes": p["tonnes"], "bounds": bounds, "scores": scores}


def rank(targets: list[dict]) -> list[dict]:
    """Attach an assessment and per-resource rank (1 = best) to every target."""
    rows = [{**t, "assessment": assess(t)} for t in targets]
    for key in RESOURCES + ["any"]:
        ordered = sorted(rows, key=lambda r: -r["assessment"]["scores"][key])
        for i, r in enumerate(ordered, 1):
            r.setdefault("ranks", {})[key] = i
    rows.sort(key=lambda r: r["ranks"]["any"])
    return rows
