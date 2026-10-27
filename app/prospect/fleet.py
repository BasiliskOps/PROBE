"""The house fleet: PROBE's own prospectors, launched at newly discovered near-Earth asteroids.

Once a day it reads the JPL feed of near-Earth asteroids with short
observation arcs (fresh discoveries), takes the largest ones no house probe
is already flying to, and designs a mission to each. Their surveys feed the
public atlas like anyone else's.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.config import settings
from app.missions import designer, store

from . import catalog

log = logging.getLogger(__name__)
HOUSE_PLAN = "house"


def picks(n: int) -> list[dict]:
    taken = store.targeted_ids()
    fresh = [t for t in catalog.new_neos() if t["id"] not in taken and t.get("H") is not None]
    fresh.sort(key=lambda t: t["H"])  # brightest first, which means largest
    return fresh[:n]


async def run_daily(now: datetime) -> list[str]:
    day = now.strftime("%Y-%m-%d")
    if store.get_meta("fleet_last_day") == day or settings.fleet_launches_per_day <= 0:
        return []
    store.set_meta("fleet_last_day", day)
    launched = []
    for t in picks(settings.fleet_launches_per_day):
        sentence = f"Prospect newly discovered asteroid {t['name']}"
        mid, _ = store.create(sentence)
        intent = {"supported": True, "kind": "asteroid", "asteroid": t["id"], "resource": "any",
                  "region": "near-earth", "arrival": "orbit", "via": [], "probe_class": "small",
                  "priority": "soonest", "objective": sentence, "source": "fleet"}
        m = await designer.design(mid, plan=HOUSE_PLAN, start=now, intent=intent)
        log.info("house probe to %s: %s", t["name"], m["status"])
        launched.append(mid)
    return launched
