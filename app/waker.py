"""Milestone waker. The model is only called when a mission reaches a milestone.

Run inside the app (a background loop) or from cron: `python -m app.waker`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.astro.search import jd_from_dt
from app.missions import flight, store
from app.swarm import agents

log = logging.getLogger(__name__)
MODEL_CALLS_PER_MISSION_PER_TICK = 3  # a long outage backfills with templates, not a burst of model calls


async def _notify(m: dict, text: str, event: dict) -> None:
    if not m.get("notify_url"):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(m["notify_url"], json={"mission_id": m["id"], "event": event["id"], "text": text})
    except Exception as exc:
        log.warning("notify failed for %s: %s", m["id"], exc)


def run_survey(m: dict, event: dict) -> dict | None:
    """Record the probe's measurements of its asteroid in the shared atlas."""
    from app.prospect import composition

    sb = m["spec"].get("small_body")
    if not sb:
        return None
    s = composition.survey(sb, event["data"]["mode"], m["id"])
    store.add_survey(m["id"], sb["id"], event["jd"], s)
    return s


async def tick_mission(m: dict, real_jd: float) -> int:
    """Advance one mission to its own mission time and send what is due."""
    jd_now = flight.sim_now(m, real_jd)
    sent = 0
    changed = bool(flight.expire_decisions(m, jd_now))
    if m["status"] == "ready" and jd_now >= m["detail"]["launch_jd"]:
        m["status"], changed = "in_flight", True
    if m["status"] == "in_flight" and jd_now >= m["detail"]["arrival_jd"]:
        m["status"], changed = "arrived", True
    done = store.messaged(m["id"])
    due = [e for e in m["events"] if e["jd"] <= jd_now and e["id"] not in done]
    recent = [r["text"] for r in store.messages(m["id"])[:3]][::-1]
    calls = 0
    for e in due:
        snap = flight.snapshot(m, e["jd"])
        dec = None
        if e["kind"] == "decision":
            dec = next((d for d in m["decisions"] if d["id"] == e["data"]["decision"]), None)
            if dec is None or dec["status"] == "decided":
                store.add_message(m["id"], e["id"], e["jd"], "decision", "Decision already settled.")
                continue
        survey = run_survey(m, e) if e["kind"] == "survey" else None
        rate = m.get("clock", {}).get("rate", 1.0)
        use_model = calls < MODEL_CALLS_PER_MISSION_PER_TICK and (jd_now - e["jd"]) < 30 * rate
        text = await agents.milestone_message(m, e, snap, dec, recent, use_model=use_model, survey=survey)
        calls += int(use_model)
        if store.add_message(m["id"], e["id"], e["jd"], e["kind"], text):
            sent += 1
            recent.append(text)
            await _notify(m, text, e)
    if changed:
        store.save(m)
    return sent


async def tick(now: datetime | None = None, fleet_enabled: bool = True) -> int:
    now = now or datetime.now(timezone.utc)
    jd_now = jd_from_dt(now)
    total = 0
    for m in store.active():
        try:
            total += await tick_mission(m, jd_now)
        except Exception:
            log.exception("waker failed for %s", m["id"])
    if fleet_enabled:
        from app.prospect import fleet

        try:
            await fleet.run_daily(now)
        except Exception:
            log.exception("house fleet failed")
    return total


async def run_forever(interval_s: int) -> None:
    while True:
        try:
            await tick()
        except Exception:
            log.exception("waker tick failed")
        await asyncio.sleep(interval_s)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"messages sent: {asyncio.run(tick())}")
