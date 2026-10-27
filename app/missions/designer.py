"""Mission design swarm: intent agent, target planner, trajectory workers, flight director and persona.

The intent agent reads the sentence. For prospecting, the planner ranks
asteroids from the live JPL catalog by expected resource against reach, and
the trajectory workers search launch windows to the best few in parallel
processes. The persona and flight director then write from the chosen design.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.astro import search as S
from app.config import settings
from app.prospect import catalog, composition, planner
from app.swarm import agents, intent as intent_agent

from . import flight, store

log = logging.getLogger(__name__)
_slots = asyncio.Semaphore(1)  # one trajectory search at a time on small hosts
ASTEROID_HORIZON_DAYS = 900.0


def _alt_summary(d: dict, label: str | None = None) -> dict:
    det = d["detail"]
    return {"target": label, "route": [flight.body_label(b) for b in det["sequence"]],
            "launch_date": S.iso(det["launch_jd"]), "arrival_date": S.iso(det["arrival_jd"]),
            "c3_km2s2": round(det["c3_km2s2"], 1), "launch_mass_kg": round(d["budget"]["wet_mass_kg"]),
            "vehicle": d["vehicle"]["name"]}


def _fail(m: dict, reason: str) -> dict:
    m.update(status="failed", error=reason)
    store.save(m)
    return m


async def _search(spec: S.MissionSpec, start: datetime, horizon: float, priority: str) -> dict:
    async with _slots:
        return await asyncio.to_thread(
            S.find_windows, spec, start, horizon, 180.0, settings.ephemeris_source, settings.data_dir,
            settings.search_workers, settings.search_maxiter, 0.15, priority)


def target_score(t: dict, resource: str, cost: float) -> float:
    """Expected resource (orders of magnitude) traded against how hard the mission is to close (cost < 1)."""
    import math

    p = composition.prior(t)["tonnes"]
    tonnes = sum(p.values()) if resource == "any" else p[resource]
    return math.log10(max(tonnes, 1.0)) - 3.0 * cost


def _targets_for(intent: dict) -> list[dict]:
    if intent.get("asteroid"):
        t = catalog.find(intent["asteroid"])
        return [t] if t else []
    return planner.candidates(intent.get("resource", "any"), intent.get("region", "near-earth"), n=3)


async def design(mission_id: str, plan: str = "free", notify_url: str | None = None,
                 start: datetime | None = None, intent: dict | None = None) -> dict:
    m = store.get(mission_id)
    m["plan"], m["notify_url"] = plan, notify_url
    try:
        it = intent or await intent_agent.parse(m["sentence"])
        m["intent"] = it
        if not it.get("supported", True):
            return _fail(m, it.get("unsupported_reason") or "That destination is not supported yet.")
        start = start or datetime.now(timezone.utc)
        dry = intent_agent.CLASSES[it.get("probe_class", "small" if it.get("kind") == "asteroid" else "medium")]
        priority = it.get("priority", "soonest")

        if it.get("kind") == "asteroid":
            targets = _targets_for(it)
            if not targets:
                return _fail(m, f"No asteroid named {it.get('asteroid')} is in the JPL catalog feed.")
            results = []
            resource = it.get("resource", "any")
            for t in targets:
                spec = S.MissionSpec(target=t["id"], arrival=it.get("arrival", "orbit"), small_body=t, dry_mass_kg=dry)
                res = await _search(spec, start, ASTEROID_HORIZON_DAYS, priority)
                if res["status"] == "ok":
                    results.append((-target_score(t, resource, res["design"]["cost"]), t, spec, res))
            if not results:
                names = ", ".join(t["name"] for t in targets)
                return _fail(m, f"No launch window in the next {int(ASTEROID_HORIZON_DAYS / 365)} years reaches {names} "
                                "on a cataloged rocket.")
            results.sort(key=lambda r: r[0])
            _, target, spec, res = results[0]
            m["target"] = target
            m["prior"] = composition.prior(target)
            m["resource"] = it.get("resource", "any")
            alternatives = [_alt_summary(r[3]["design"], r[1]["name"]) for r in results[1:]]
        else:
            spec = S.MissionSpec(target=it["target"], arrival=it["arrival"], via=it.get("via", []), dry_mass_kg=dry)
            res = await _search(spec, start, settings.search_horizon_days, priority)
            if res["status"] != "ok":
                return _fail(m, "No launch window in the next three years closes on a cataloged rocket.")
            alternatives = [_alt_summary(a) for a in res["alternatives"]]

        d, table = res["design"], res["table"]
        m["spec"] = {"target": spec.target, "arrival": spec.arrival, "via": spec.via, "dry_mass_kg": spec.dry_mass_kg,
                     "isp_s": spec.isp_s, "capture_period_days": None, "small_body": spec.small_body}
        m["design"] = {"sequence": d["sequence"], "x": d["x"],
                       "ephemeris": {"source": table.source, "jd_start": table.jd0, "jd_end": table.jd_end}}
        m["detail"], m["budget"], m["budget_now"], m["vehicle"] = d["detail"], d["budget"], d["budget"], d["vehicle"]
        b = d["budget"]
        m["margin_dv_kms"] = b["total_dv_kms"] - (b["dsm_dv_kms"] + b["arrival_dv_kms"] + b["tour_dv_kms"]
                                                   + b["nav_dv_kms"])
        m["alternatives"] = alternatives
        m["search"] = {"routes_and_bins": res["searched"], "ephemeris": table.source}
        real_jd = S.jd_from_dt(start)
        m["clock"] = {"real0": real_jd, "sim0": real_jd, "rate": settings.mission_clock}
        m["decisions"] = flight.build_decisions(m) if plan != "free" else []
        m["events"] = flight.timeline(m)
        persona, brief = await asyncio.gather(agents.persona(m, it), agents.brief(m))
        m["persona"], m["brief"] = persona, brief
        m["status"] = "ready"
        store.save(m)
        store.add_message(m["id"], "designed", real_jd, "designed", persona["launch_message"])
        return m
    except Exception as exc:
        log.exception("design failed for %s", mission_id)
        return _fail(m, f"Design failed: {exc.__class__.__name__}")
