"""Pick asteroid targets for a prospecting request.

Candidates are ranked by expected tonnes of the requested resource against a
quick reachability estimate (Hohmann transfer from 1 AU, plus plane change
and eccentricity terms). Only the top few get the full trajectory search.
"""
from __future__ import annotations

import math

from app.astro.constants import AU_KM, MU_SUN

from . import catalog, composition


def reach_dv_kms(t: dict) -> float:
    """Rough rendezvous cost from Earth's orbit, for ranking only."""
    r1, r2 = AU_KM, t["a"] * AU_KM
    v1 = math.sqrt(MU_SUN / r1)
    at = (r1 + r2) / 2
    hoh = abs(math.sqrt(MU_SUN * (2 / r1 - 1 / at)) - v1) + abs(math.sqrt(MU_SUN / r2) - math.sqrt(MU_SUN * (2 / r2 - 1 / at)))
    plane = 2 * math.sqrt(MU_SUN / r2) * math.sin(math.radians(t["i"]) / 2)
    return hoh + plane + 6.0 * t["e"]


def in_region(t: dict, region: str) -> bool:
    if region == "near-earth":
        return t.get("neo") or t["a"] * (1 - t["e"]) < 1.3
    if region == "main-belt":
        return 2.1 <= t["a"] <= 3.3
    return True


def candidates(resource: str, region: str = "near-earth", n: int = 3) -> list[dict]:
    pool = [t for t in catalog.all_targets() if in_region(t, region)] or catalog.all_targets()
    scored = []
    for t in pool:
        p = composition.prior(t)
        tonnes = sum(p["tonnes"].values()) if resource == "any" else p["tonnes"][resource]
        scored.append((math.log10(max(tonnes, 1.0)) - 1.2 * reach_dv_kms(t), t))
    scored.sort(key=lambda s: -s[0])
    return [t for _, t in scored[:n]]
