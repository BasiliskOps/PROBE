"""One collection run: the swarm pulls every source, the ranking runs, and the
published dataset is written for the interface.

    python -m app.collect.run            # writes site/data/system.json and site/data/manifest.json

Order: catalog and ephemeris agents run concurrently; the catalog is ranked;
the physical agent pulls measured mass, density and diameter for the leading
candidates, which replace the catalog-derived values; the ranking runs again;
the imagery agent pulls mission imagery for spacecraft-visited bodies.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.prospect import rank as R

from . import agents

log = logging.getLogger(__name__)
G = 6.6743e-11
OUT = Path(__file__).resolve().parents[2] / "site" / "data"


def jd_now() -> float:
    return datetime.now(timezone.utc).timestamp() / 86400.0 + 2440587.5


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def apply_measured(t: dict, phys: dict) -> dict:
    """Replace catalog-derived values with measured ones where a reference exists."""
    t = dict(t)
    measured = {}
    gm = _f(phys.get("GM", {}).get("value"))
    if gm:
        t["mass_kg"] = gm * 1e9 / G
        measured["mass"] = phys["GM"]
    rho = _f(phys.get("density", {}).get("value"))
    if rho:
        t["density"] = rho
        measured["density"] = phys["density"]
    d = _f(phys.get("diameter", {}).get("value"))
    if d:
        t["diameter_km"] = d
        t["diameter_measured"] = True
        measured["diameter"] = phys["diameter"]
    if phys.get("rot_per"):
        measured["rotation"] = phys["rot_per"]
    t["measured"] = measured
    return t


def sig(x: float, n: int = 3) -> float:
    return float(f"{x:.{n}g}")


def publish_row(r: dict, imagery: dict) -> dict:
    a = r["assessment"]
    row = {
        "id": r["id"], "name": r["name"],
        "el": [r["epoch"], sig(r["a"], 8), sig(r["e"], 7), sig(r["i"], 6), sig(r["om"], 7), sig(r["w"], 7),
               sig(r["ma"], 7)],
        "d": sig(r["diameter_km"]), "dm": bool(r.get("diameter_measured")),
        "alb": r.get("albedo"), "cls": r.get("spectral_class"), "tax": r.get("taxonomy"),
        "grp": a["group"], "basis": a["basis"], "neo": bool(r.get("neo")), "pha": bool(r.get("pha")),
        "oc": r.get("orbit_class"), "dv": sig(a["dv"]), "mass": sig(a["mass_kg"]),
        "t": {k: sig(v) for k, v in a["tonnes"].items()},
        "lo": {k: sig(v[0]) for k, v in a["bounds"].items()},
        "hi": {k: sig(v[1]) for k, v in a["bounds"].items()},
        "rk": r["ranks"],
    }
    if r.get("measured"):
        row["meas"] = r["measured"]
    if r["id"] in imagery:
        row["img"] = imagery[r["id"]]
    return row


async def collect(top_physical: int = 150) -> dict:
    jd = jd_now()
    cat, eph = await asyncio.gather(agents.catalog_agent(), agents.ephemeris_agent(jd))
    if not cat["records"]:
        raise SystemExit(f"catalog agent returned nothing ({cat['error']}); refusing to publish an empty dataset")
    ranked = R.rank(cat["records"])
    lead = [r["id"] for r in ranked[:top_physical]]
    lead += [i for i in agents.VISITED if i not in lead and any(r["id"] == i for r in ranked)]
    phys = await agents.physical_agent(lead)
    targets = [apply_measured(t, phys["records"][t["id"]]) if t["id"] in phys["records"] else t
               for t in cat["records"]]
    ranked = R.rank(targets)
    img = await agents.imagery_agent([r for r in ranked if r["id"] in agents.VISITED])
    runs = [cat, eph, phys, img]
    system = {
        "generated_at": agents._now(), "epoch_jd": jd,
        "planets": eph["records"],
        "bodies": [publish_row(r, img["records"]) for r in ranked],
        "resources": R.RESOURCES,
    }
    manifest = {
        "generated_at": system["generated_at"], "epoch_jd": jd,
        "agents": [{k: v for k, v in run.items() if k != "records"} for run in runs],
        "method": {
            "composition": "Spectral class, or albedo when no class is measured, mapped to meteorite analog "
                           "groups with published mass-fraction ranges (app/prospect/composition.py).",
            "mass": "Measured GM and density from the JPL SBDB where published, otherwise diameter and the "
                    "group's mean bulk density.",
            "reach": "Rough rendezvous cost from Earth's orbit (Hohmann, plane change, eccentricity term), "
                     "for ordering only.",
            "ranking": "log10(expected tonnes) - 1.2 x reach in km/s, per resource and overall.",
        },
    }
    return {"system": system, "manifest": manifest}


def write(out: dict, dest: Path = OUT) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "system.json").write_text(json.dumps(out["system"], separators=(",", ":")))
    (dest / "manifest.json").write_text(json.dumps(out["manifest"], indent=1))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=150, help="candidates enriched with measured parameters")
    args = ap.parse_args()
    out = asyncio.run(collect(args.top))
    write(out)
    for a in out["manifest"]["agents"]:
        log.info("%-10s %6s records  %5ss  %s", a["agent"], a["count"], a["seconds"], a["error"] or "ok")


if __name__ == "__main__":
    main()
