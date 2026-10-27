from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl

from app.astro.search import iso, jd_from_dt
from app.missions import designer, flight, patch, store

router = APIRouter()


class MissionRequest(BaseModel):
    sentence: str = Field(min_length=8, max_length=400)
    notify_url: HttpUrl | None = None


class Decision(BaseModel):
    decision_id: str
    option_id: str


def now_jd() -> float:
    return jd_from_dt(datetime.now(timezone.utc))


def asteroid_view(t: dict) -> dict:
    from app.prospect import composition

    p = composition.prior(t)
    return {"id": t["id"], "name": t["name"], "spectral_class": t.get("spectral_class"),
            "taxonomy": t.get("taxonomy"), "diameter_km": round(t["diameter_km"], 3),
            "diameter_measured": t.get("diameter_measured"), "albedo": t.get("albedo"), "near_earth": t.get("neo"),
            "potentially_hazardous": t.get("pha"), "orbit": {k: t[k] for k in ("a", "e", "i")},
            "composition_group": p["group"], "group_basis": p["basis"],
            "expected_tonnes": {k: float(f"{v:.3g}") for k, v in p["tonnes"].items()}}


def atlas_entry(target_id: str) -> dict | None:
    from app.prospect import composition

    ss = store.surveys(target_id)
    if not ss:
        return None
    c = composition.combine(ss)
    return {"surveys": c["surveys"], "relative_uncertainty": round(c["relative_uncertainty"], 3),
            "tonnes": {k: float(f"{v:.3g}") for k, v in c["tonnes"].items()},
            "probes": sorted({s["mission_id"] for s in ss})}


def public_view(m: dict, real_jd: float, owner: bool = False) -> dict:
    out = {"id": m["id"], "status": m["status"], "sentence": m["sentence"], "plan": m.get("plan", "free")}
    if m["status"] == "failed":
        out["error"] = m.get("error")
        return out
    if m["status"] == "designing":
        return out
    jd_now = flight.sim_now(m, real_jd)
    flight.mission_table(m)  # registers an asteroid target so its name resolves
    det = m["detail"]
    sb = m["spec"].get("small_body")
    if sb:
        mine = [s for s in store.surveys(sb["id"]) if s["mission_id"] == m["id"]]
        out["asteroid"] = asteroid_view(sb)
        out["prospecting_for"] = m.get("resource", "any")
        out["findings"] = ({"mode": mine[0]["mode"], "diameter_km": round(mine[0]["diameter_km"], 4),
                            "group": mine[0]["group"], "relative_uncertainty": mine[0]["sigma"],
                            "tonnes": {k: float(f"{v:.3g}") for k, v in mine[0]["tonnes"].items()}} if mine else None)
        out["atlas"] = atlas_entry(sb["id"])
    out["mission_time"] = {"date": iso(jd_now), "jd": jd_now, "rate": m.get("clock", {}).get("rate", 1.0)}
    out.update({
        "probe": {"name": m["persona"]["name"], "personality": m["persona"]["personality"]},
        "brief": m["brief"],
        "route": [flight.body_label(b) for b in det["sequence"]],
        "launch": {"date": iso(det["launch_jd"]), "vehicle": m["vehicle"], "c3_km2s2": round(det["c3_km2s2"], 2),
                   "dla_deg": round(det["dla_deg"], 1)},
        "arrival": {"date": iso(det["arrival_jd"]), "body": sb["name"] if sb else m["spec"]["target"],
                    "mode": ("rendezvous" if m["spec"]["arrival"] == "orbit" else "flyby") if sb else m["spec"]["arrival"],
                    "vinf_kms": round(det["vinf_arr_kms"], 2), "burn_ms": round(det["arrival_dv_kms"] * 1000)},
        "flybys": [{"body": flight.body_label(f["body"]), "date": iso(f["jd"]), "altitude_km": round(f["altitude_km"]),
                    "speed_kms": round(f["vinf_kms"], 2)} for f in det["flybys"]],
        "maneuvers": [{"date": iso(d["jd"]), "dv_ms": round(d["dv_kms"] * 1000)} for d in det["dsms"]
                      if d["dv_kms"] >= 0.005],
        "budget": {k: round(v, 3) for k, v in m["budget"].items()},
        "now": flight.snapshot(m, jd_now),
        "timeline": [{"date": iso(e["jd"]), "title": e["title"], "kind": e["kind"], "done": e["jd"] <= jd_now}
                     for e in m["events"]],
        "decisions": flight.open_decisions(m, jd_now),
        "alternatives": m.get("alternatives", []),
        "ephemeris": m["design"]["ephemeris"]["source"],
        "patch_url": f"/api/v1/missions/{m['id']}/patch.svg",
    })
    if not owner:
        for d in out["decisions"]:
            d["options"] = [{k: v for k, v in o.items() if k != "set"} for o in d["options"]]
    return out


async def run_design(sentence: str, plan: str, notify_url: str | None = None) -> tuple[dict, str]:
    mid, token = store.create(sentence)
    m = await designer.design(mid, plan=plan, notify_url=notify_url)
    return m, token


@router.post("/missions/design")
async def design_mission(req: MissionRequest):
    """Paid per call over x402. Returns the designed mission and the owner token for decisions."""
    m, token = await run_design(req.sentence, plan="api", notify_url=str(req.notify_url) if req.notify_url else None)
    if m["status"] == "failed":
        raise HTTPException(status_code=422, detail=m.get("error"))
    return {"owner_token": token, "mission": public_view(m, now_jd(), owner=True)}


def _mission(mid: str) -> dict:
    m = store.get(mid)
    if m is None:
        raise HTTPException(status_code=404, detail="no such mission")
    return m


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    return public_view(_mission(mission_id), now_jd())


@router.get("/missions/{mission_id}/track")
async def get_track(mission_id: str):
    m = _mission(mission_id)
    if m["status"] in ("designing", "failed"):
        raise HTTPException(status_code=409, detail="mission has no trajectory")
    jd = flight.sim_now(m, now_jd())
    events = [{"title": e["title"], "date": iso(e["jd"]), "position": flight.ecliptic_au(flight.position(m, e["jd"])["r_km"])}
              for e in m["events"] if e["kind"] in ("launch", "flyby", "arrival", "maneuver")]
    return {"track": flight.track(m), "now": flight.snapshot(m, jd), "events": events,
            "target": flight.target_orbit(m, jd),
            "route": m["detail"]["sequence"], "launch_jd": m["detail"]["launch_jd"],
            "arrival_jd": m["detail"]["arrival_jd"], "jd_now": jd}


@router.get("/missions/{mission_id}/messages")
async def get_messages(mission_id: str):
    _mission(mission_id)
    return [{"date": iso(r["jd"]), "kind": r["kind"], "text": r["text"]} for r in store.messages(mission_id)]


@router.get("/missions/{mission_id}/patch.svg")
async def get_patch(mission_id: str):
    m = _mission(mission_id)
    if m["status"] in ("designing", "failed"):
        raise HTTPException(status_code=409, detail="mission has no trajectory")
    return Response(patch.svg(m), media_type="image/svg+xml")


def apply_decision(mission_id: str, decision_id: str, option_id: str, token: str | None) -> dict:
    m = _mission(mission_id)
    if not store.is_owner(mission_id, token):
        raise HTTPException(status_code=403, detail="owner token required")
    if m.get("plan", "free") == "free":
        raise HTTPException(status_code=402, detail="decision points come with the fleet plan")
    try:
        dec = flight.decide(m, decision_id, option_id, flight.sim_now(m, now_jd()))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc).strip("'"))
    store.save(m)
    return {"decision": {k: v for k, v in dec.items() if k != "options"},
            "margin_ms": round(flight.margin_kms(m) * 1000, 1), "arrival": iso(m["detail"]["arrival_jd"])}


@router.post("/missions/{mission_id}/decisions")
async def decide(mission_id: str, decision: Decision, x_owner_token: str | None = Header(default=None)):
    return apply_decision(mission_id, decision.decision_id, decision.option_id, x_owner_token)


@router.get("/sky")
async def sky(jd: float | None = None):
    jd = jd if jd and 2451545.0 <= jd <= 2469807.0 else now_jd()
    return {"jd": jd, "date": iso(jd), "planets": flight.sky(jd)}


@router.get("/atlas")
async def atlas():
    """Every asteroid any probe has surveyed, with the combined estimate across probes."""
    from app.prospect import catalog

    by_id = {t["id"]: t for t in catalog.all_targets()}
    out = []
    for tid in sorted({s["target_id"] for s in store.surveys()}):
        t = by_id.get(tid)
        out.append({"asteroid": asteroid_view(t) if t else {"id": tid}, "measured": atlas_entry(tid)})
    return {"note": "Measurements are simulated from each asteroid's catalog data and spectral class.",
            "asteroids": out}


@router.get("/targets")
async def targets(resource: str = "any", region: str = "near-earth", n: int = 10):
    """Best prospecting targets in the live JPL catalog for a resource."""
    from app.prospect import planner

    n = max(1, min(n, 50))
    return [{**asteroid_view(t), "reach_dv_kms_estimate": round(planner.reach_dv_kms(t), 2)}
            for t in planner.candidates(resource, region, n)]
