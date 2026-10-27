"""Mission design swarm: intent agent, parallel trajectory workers, flight director and persona.

The intent agent reads the sentence, the trajectory workers search every
candidate route across the launch horizon in parallel processes, and the
persona agent drafts the probe's character while they run. The flight
director then writes the brief from the chosen design.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.astro import search as S
from app.config import settings
from app.swarm import agents, intent as intent_agent

from . import flight, store

log = logging.getLogger(__name__)
_slots = asyncio.Semaphore(1)  # one trajectory search at a time on small hosts


def _alt_summary(d: dict) -> dict:
    det = d["detail"]
    return {"route": det["sequence"], "launch_date": S.iso(det["launch_jd"]), "arrival_date": S.iso(det["arrival_jd"]),
            "c3_km2s2": round(det["c3_km2s2"], 1), "launch_mass_kg": round(d["budget"]["wet_mass_kg"]),
            "vehicle": d["vehicle"]["name"]}


def _fail(m: dict, reason: str) -> dict:
    m.update(status="failed", error=reason)
    store.save(m)
    return m


async def design(mission_id: str, plan: str = "free", notify_url: str | None = None,
                 start: datetime | None = None) -> dict:
    m = store.get(mission_id)
    m["plan"], m["notify_url"] = plan, notify_url
    try:
        it = await intent_agent.parse(m["sentence"])
        m["intent"] = it
        if not it.get("supported", True):
            return _fail(m, it.get("unsupported_reason") or "That destination is not supported yet.")
        spec = S.MissionSpec(target=it["target"], arrival=it["arrival"], via=it.get("via", []),
                             dry_mass_kg=intent_agent.CLASSES[it.get("probe_class", "medium")])
        start = start or datetime.now(timezone.utc)
        async with _slots:
            res = await asyncio.to_thread(
                S.find_windows, spec, start, settings.search_horizon_days, 180.0, settings.ephemeris_source,
                settings.data_dir, settings.search_workers, settings.search_maxiter, 0.15, it.get("priority", "soonest"))
        if res["status"] != "ok":
            return _fail(m, "No launch window in the next three years closes on a cataloged rocket.")
        d, table = res["design"], res["table"]
        m["spec"] = {"target": spec.target, "arrival": spec.arrival, "via": spec.via,
                     "dry_mass_kg": spec.dry_mass_kg, "isp_s": spec.isp_s, "capture_period_days": None}
        m["design"] = {"sequence": d["sequence"], "x": d["x"],
                       "ephemeris": {"source": table.source, "jd_start": table.jd0, "jd_end": table.jd_end}}
        m["detail"], m["budget"], m["budget_now"], m["vehicle"] = d["detail"], d["budget"], d["budget"], d["vehicle"]
        b = d["budget"]
        m["margin_dv_kms"] = b["total_dv_kms"] - (b["dsm_dv_kms"] + b["arrival_dv_kms"] + b["tour_dv_kms"]
                                                   + b["nav_dv_kms"])
        m["alternatives"] = [_alt_summary(a) for a in res["alternatives"]]
        m["search"] = {"routes_and_bins": res["searched"], "ephemeris": table.source}
        m["decisions"] = flight.build_decisions(m) if plan != "free" else []
        m["events"] = flight.timeline(m)
        persona, brief = await asyncio.gather(agents.persona(m, it), agents.brief(m))
        m["persona"], m["brief"] = persona, brief
        m["status"] = "ready"
        store.save(m)
        store.add_message(m["id"], "designed", S.jd_from_dt(start),
                          "designed", persona["launch_message"])
        return m
    except Exception as exc:
        log.exception("design failed for %s", mission_id)
        return _fail(m, f"Design failed: {exc.__class__.__name__}")
