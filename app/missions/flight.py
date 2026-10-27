"""A designed mission in flight: where the probe is, what happens next, and owner decisions.

Everything here is recomputed from the stored design vector, so a decision
that changes the trajectory changes every future position and milestone.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from app.astro import search as S
from app.astro.constants import AU_KM, BODY, CAPTURE, MOONS, MU_SUN, OBLIQUITY_DEG, PLANETS
from app.astro.ephemeris import EphemerisTable, load_table
from app.astro.mga import capture_dv, kepler
from app.config import settings

_EPS = math.radians(OBLIQUITY_DEG)
_ROT = np.array([[1, 0, 0], [0, math.cos(_EPS), math.sin(_EPS)], [0, -math.sin(_EPS), math.cos(_EPS)]])

CROSSINGS_OUT = [("mars", 1.524, "Crossed the orbit of Mars"), ("belt-in", 2.2, "Entered the main asteroid belt"),
                 ("belt-out", 3.3, "Cleared the main asteroid belt"), ("jupiter", 5.203, "Crossed the orbit of Jupiter"),
                 ("saturn", 9.537, "Crossed the orbit of Saturn"), ("uranus", 19.19, "Crossed the orbit of Uranus")]
CROSSINGS_IN = [("venus", 0.723, "Crossed inside the orbit of Venus"),
                ("mercury", 0.387, "Crossed inside the orbit of Mercury")]


def ecliptic_au(r_km) -> list[float]:
    return (_ROT @ np.asarray(r_km, dtype=float) / AU_KM).tolist()


@lru_cache(maxsize=16)
def _table(source: str, jd_start: float, jd_end: float) -> EphemerisTable:
    src = "horizons" if source == "JPL Horizons" else "de421"
    return load_table(jd_start, jd_end, source=src, cache_dir=settings.data_dir)


def mission_table(m: dict) -> EphemerisTable:
    e = m["design"]["ephemeris"]
    table = _table(e["source"], e["jd_start"], e["jd_end"])
    sb = m["spec"].get("small_body")
    if sb:
        from app.astro.smallbody import extend

        table = extend(table, sb)
    return table


SURVEY_DAYS = 60.0  # mission days a rendezvous probe spends mapping before it reports


def body_label(name: str) -> str:
    return BODY.get(name, {}).get("label") or name.title()


def sim_now(m: dict, real_jd: float) -> float:
    """Mission time. A mission clock rate of 30 flies a month of mission per real day."""
    c = m.get("clock")
    if not c:
        return real_jd
    return c["sim0"] + (real_jd - c["real0"]) * c["rate"]


def spec_of(m: dict) -> S.MissionSpec:
    return S.MissionSpec(**m["spec"])


def redesign(m: dict) -> None:
    """Recompute geometry, budget and milestones from the current design vector."""
    d = S.evaluate_design(m["design"]["sequence"], m["design"]["x"], mission_table(m), spec_of(m))
    m["detail"], m["budget_now"] = d["detail"], d["budget"]
    m["events"] = timeline(m)


def planet_state(m: dict, name: str, jd: float):
    """Planet state at any date: the mission table when it covers jd, else a small table around jd."""
    sb = m["spec"].get("small_body")
    if sb and name.startswith("sb:"):
        from app.astro import smallbody

        return smallbody.state(sb, jd)
    table = mission_table(m)
    if not (table.jd0 <= jd <= table.jd_end - 1):
        e = m["design"]["ephemeris"]
        table = _table(e["source"], math.floor(jd) - 2, math.floor(jd) + 2)
    return table.state(name, jd)


def position(m: dict, jd: float) -> dict:
    det = m["detail"]
    if jd <= det["launch_jd"]:
        r, _ = planet_state(m, "earth", jd)
        return {"phase": "prelaunch", "r_km": r.tolist()}
    if jd >= det["arrival_jd"]:
        r, _ = planet_state(m, spec_of(m).planet, jd)
        phase = "orbit" if spec_of(m).arrival == "orbit" else "departed"
        if phase == "departed":
            last = det["arcs"][-1]
            r, _ = kepler(np.array(last["r0_km"]), np.array(last["v0_kms"]),
                          (jd - last["jd_start"]) * 86400.0, MU_SUN)
            r = np.asarray(r)
        return {"phase": phase, "r_km": r.tolist()}
    for arc in det["arcs"]:
        if arc["jd_start"] <= jd <= arc["jd_end"]:
            r, v = kepler(np.array(arc["r0_km"]), np.array(arc["v0_kms"]), (jd - arc["jd_start"]) * 86400.0, MU_SUN)
            return {"phase": "cruise", "r_km": r.tolist(), "v_kms": v.tolist(), "leg": arc["leg"]}
    return {"phase": "cruise", "r_km": det["arcs"][-1]["r0_km"]}


def track(m: dict, points_per_year: int = 120) -> list[list[float]]:
    out = []
    for arc in m["detail"]["arcs"]:
        span = arc["jd_end"] - arc["jd_start"]
        n = max(4, int(span / 365.25 * points_per_year))
        r0, v0 = np.array(arc["r0_km"]), np.array(arc["v0_kms"])
        for k in range(n + 1):
            r, _ = kepler(r0, v0, span * k / n * 86400.0, MU_SUN)
            out.append(ecliptic_au(r) + [arc["jd_start"] + span * k / n])
    return out


def _crossings(m: dict) -> list[dict]:
    events, seen = [], set()
    prev = None
    for arc in m["detail"]["arcs"]:
        r0, v0 = np.array(arc["r0_km"]), np.array(arc["v0_kms"])
        span = arc["jd_end"] - arc["jd_start"]
        n = max(2, int(span / 2))
        for k in range(n + 1):
            jd = arc["jd_start"] + span * k / n
            r, _ = kepler(r0, v0, (jd - arc["jd_start"]) * 86400.0, MU_SUN)
            d = float(np.linalg.norm(r)) / AU_KM
            if prev is not None:
                for key, a, title in CROSSINGS_OUT:
                    if prev < a <= d and key not in seen:
                        seen.add(key)
                        events.append({"id": f"cross-{key}", "kind": "crossing", "jd": jd, "title": title,
                                       "data": {"distance_au": round(a, 3)}})
                for key, a, title in CROSSINGS_IN:
                    if prev > a >= d and key not in seen:
                        seen.add(key)
                        events.append({"id": f"cross-{key}", "kind": "crossing", "jd": jd, "title": title,
                                       "data": {"distance_au": round(a, 3)}})
            prev = d
    return events


def timeline(m: dict) -> list[dict]:
    det, spec = m["detail"], spec_of(m)
    ev = [{"id": "launch", "kind": "launch", "jd": det["launch_jd"],
           "title": f"Launch on {m['vehicle']['name']}",
           "data": {"c3_km2s2": round(det["c3_km2s2"], 2), "vehicle": m["vehicle"]["name"]}}]
    for i, d in enumerate(det["dsms"]):
        if d["dv_kms"] >= 0.005:
            ev.append({"id": f"dsm-{i}", "kind": "maneuver", "jd": d["jd"], "title": "Deep-space maneuver",
                       "data": {"dv_ms": round(d["dv_kms"] * 1000)}})
    for i, f in enumerate(det["flybys"]):
        ev.append({"id": f"flyby-{i}", "kind": "flyby", "jd": f["jd"], "title": f"{body_label(f['body'])} flyby",
                   "data": {"body": f["body"], "altitude_km": round(f["altitude_km"]),
                            "speed_kms": round(f["vinf_kms"], 2)}})
    ev += _crossings(m)
    planet = spec.planet
    name = body_label(planet)
    if spec.small_body:
        if spec.arrival == "orbit":
            ev.append({"id": "arrival", "kind": "arrival", "jd": det["arrival_jd"], "title": f"Rendezvous with {name}",
                       "data": {"dv_ms": round(det["arrival_dv_kms"] * 1000), "vinf_kms": round(det["vinf_arr_kms"], 2)}})
            ev.append({"id": "survey", "kind": "survey", "jd": det["arrival_jd"] + SURVEY_DAYS,
                       "title": f"Survey of {name} complete", "data": {"mode": "rendezvous"}})
        else:
            ev.append({"id": "arrival", "kind": "arrival", "jd": det["arrival_jd"], "title": f"{name} flyby",
                       "data": {"vinf_kms": round(det["vinf_arr_kms"], 2)}})
            ev.append({"id": "survey", "kind": "survey", "jd": det["arrival_jd"] + 1,
                       "title": f"Flyby data from {name} downlinked", "data": {"mode": "flyby"}})
    elif spec.arrival == "orbit":
        ev.append({"id": "arrival", "kind": "arrival", "jd": det["arrival_jd"],
                   "title": f"{name} orbit insertion",
                   "data": {"dv_ms": round(det["arrival_dv_kms"] * 1000), "vinf_kms": round(det["vinf_arr_kms"], 2)}})
        period = spec.capture_period_days or CAPTURE[planet]["period_days"]
        if spec.target in MOONS:
            ev.append({"id": "tour", "kind": "science", "jd": det["arrival_jd"] + period,
                       "title": f"{spec.target.title()} campaign begins", "data": {"target": spec.target}})
        else:
            ev.append({"id": "science", "kind": "science", "jd": det["arrival_jd"] + period,
                       "title": "First science orbit complete", "data": {"period_days": period}})
    else:
        ev.append({"id": "arrival", "kind": "arrival", "jd": det["arrival_jd"], "title": f"{name} flyby",
                   "data": {"vinf_kms": round(det["vinf_arr_kms"], 2)}})
    for dec in m.get("decisions", []):
        ev.append({"id": f"decision-{dec['id']}", "kind": "decision", "jd": dec["opens_jd"],
                   "title": dec["question"], "data": {"decision": dec["id"]}})
    return sorted(ev, key=lambda e: e["jd"])


# ---------------------------------------------------------------- decisions

def _rp_index(flyby_i: int) -> int:
    return 7 + 4 * flyby_i  # x layout: [t0,u,v,vinf, eta1,T1, beta,rp,eta,T, ...]


def _maneuvers(m: dict, x: list[float], spec: S.MissionSpec) -> float:
    d = S.evaluate_design(m["design"]["sequence"], x, mission_table(m), spec)["detail"]
    return d["dsm_dv_kms"] + d["arrival_dv_kms"]


def _dv_fn(m: dict, spec: S.MissionSpec):
    from app.astro.mga import evaluate

    table = mission_table(m)
    seq = np.array([table.names.index(b) for b in m["design"]["sequence"]], dtype=np.int64)
    capture, cap_rp, cap_period = S.capture_params(spec)
    mus = np.array([BODY[p]["mu"] for p in table.names])
    rpmins = np.array([BODY[p]["rp_min"] for p in table.names])

    def dv(x) -> float:
        try:
            ok, _, _, total, _ = evaluate(np.asarray(x, dtype=float), seq, mus, rpmins, table.pos, table.vel,
                                          table.jd0, table.step, MU_SUN, capture, cap_rp, cap_period)
        except Exception:
            return 1e6
        return total if ok else 1e6

    return dv


def _reoptimize(dv, x: list[float], free: list[int], bounds: list[tuple[float, float]]) -> tuple[list[float], float]:
    """Re-solve the free variables of a design vector with everything else held."""
    from scipy.optimize import minimize

    base = np.array(x, dtype=float)

    def f(z):
        y = base.copy()
        y[free] = z
        return dv(y)

    start = np.clip(base[free], [b[0] for b in bounds], [b[1] for b in bounds])
    res = minimize(f, start, method="Powell", bounds=bounds, options={"maxfev": 4000, "xtol": 1e-7})
    y = base.copy()
    y[free] = res.x if res.fun <= f(start) else start
    return y.tolist(), float(dv(y))


def closer_flyby(m: dict, i: int, budget_kms: float) -> dict | None:
    """Lowest periapsis for flyby i the probe can buy with budget_kms.

    Everything after the flyby is re-solved: plane angles, later periapses, DSM
    timing and leg durations (within -20 %/+25 %), so the arrival date can move.
    """
    spec = spec_of(m)
    dv = _dv_fn(m, spec)
    x0 = list(m["design"]["x"])
    base = dv(x0)
    idx = _rp_index(i)
    n_legs = len(m["design"]["sequence"]) - 1
    free, bounds = [idx - 1, idx + 1, idx + 2], [(-math.pi, math.pi), (0.01, 0.99), (0.8 * x0[idx + 2], 1.25 * x0[idx + 2])]
    for leg in range(i + 2, n_legs):
        b = 6 + 4 * (leg - 1)
        free += [b, b + 1, b + 2, b + 3]
        bounds += [(-math.pi, math.pi), (1.0, 30.0), (0.01, 0.99), (0.8 * x0[b + 3], 1.25 * x0[b + 3])]
    current = x0[idx]
    for r in np.linspace(1.0, 0.8 * current, 6):
        x = list(x0)
        x[idx] = float(r)
        x, d = _reoptimize(dv, x, free, bounds)
        if d - base <= budget_kms:
            return {"x": x, "rp_ratio": float(r), "cost_kms": max(0.0, d - base)}
    return None


def _capture_decision(m: dict) -> dict | None:
    spec, det = spec_of(m), m["detail"]
    if spec.arrival != "orbit" or spec.small_body:
        return None
    p0 = CAPTURE[spec.planet]["period_days"]
    _, rp, _ = S.capture_params(S.MissionSpec(**{**m["spec"], "capture_period_days": None}))
    mu = BODY[spec.planet]["mu"]
    v = det["vinf_arr_kms"]
    current = spec.capture_period_days or p0
    dv0 = capture_dv(v, mu, rp, current * 86400.0)
    opts = []
    for frac, label in ((1.0, "planned"), (0.5, "half"), (0.25, "quarter")):
        p = p0 * frac
        cost = max(0.0, capture_dv(v, mu, rp, p * 86400.0) - dv0)
        opts.append({"id": label, "label": f"Capture into a {round(p)}-day orbit", "dv_ms": round(cost * 1000, 1),
                     "set": {"capture_period_days": p}, "first_science_jd": det["arrival_jd"] + p})
    return {"id": "capture", "kind": "capture", "opens_jd": det["arrival_jd"] - 120,
            "deadline_jd": det["arrival_jd"] - 30, "question": f"How hard should we brake at {spec.planet.title()}?",
            "options": opts, "default": "planned", "status": "pending", "chosen": None}


def build_decisions(m: dict) -> list[dict]:
    """Physically costed choices: a closer flyby, or a faster capture orbit."""
    spec = spec_of(m)
    det = m["detail"]
    out = []
    for i, f in enumerate(det["flybys"]):
        if m["design"]["x"][_rp_index(i)] < 1.3:
            continue  # already at the safe floor
        opt = closer_flyby(m, i, margin_kms(m))
        if opt is None or opt["rp_ratio"] > 0.8 * m["design"]["x"][_rp_index(i)]:
            continue  # the reserve cannot buy a pass meaningfully closer
        alt = opt["rp_ratio"] * BODY[f["body"]]["rp_min"] - BODY[f["body"]]["radius"]
        new_arrival = S.evaluate_design(m["design"]["sequence"], opt["x"], mission_table(m), spec)["detail"]["arrival_jd"]
        shift = round(new_arrival - det["arrival_jd"])
        when = (f"arrive {abs(shift)} days {'later' if shift > 0 else 'earlier'}" if abs(shift) >= 1
                else "same arrival date")
        out.append({
            "id": f"flyby-{i}", "kind": "flyby", "opens_jd": f["jd"] - 60, "deadline_jd": f["jd"] - 14,
            "question": f"Spend propellant to pass {body_label(f['body'])} at {round(alt):,} km instead of "
                        f"{round(f['altitude_km']):,} km?",
            "options": [
                {"id": "closer", "label": f"Go in to {round(alt):,} km and {when}",
                 "dv_ms": round(opt["cost_kms"] * 1000, 1), "arrival_shift_days": shift, "set": {"x": opt["x"]}},
                {"id": "planned", "label": f"Hold the planned {round(f['altitude_km']):,} km pass and save it",
                 "dv_ms": 0.0, "set": None},
            ],
            "default": "planned",
        })
    cap = _capture_decision(m)
    if cap:
        out.append(cap)
    for d in out:
        d["status"] = "pending"
        d["chosen"] = None
    return out


def margin_kms(m: dict) -> float:
    return m["margin_dv_kms"] - sum(d.get("spent_kms", 0.0) for d in m.get("decisions", []))


def decide(m: dict, decision_id: str, option_id: str, jd_now: float, by: str = "owner") -> dict:
    dec = next((d for d in m["decisions"] if d["id"] == decision_id), None)
    if dec is None:
        raise KeyError("no such decision")
    if dec["status"] == "decided":
        raise ValueError("decision already made")
    if jd_now < dec["opens_jd"] and by == "owner":
        raise ValueError("decision is not open yet")
    if jd_now > dec["deadline_jd"] and by == "owner":
        raise ValueError("decision window has closed")
    opt = next((o for o in dec["options"] if o["id"] == option_id), None)
    if opt is None:
        raise KeyError("no such option")
    before = m["detail"]["dsm_dv_kms"] + m["detail"]["arrival_dv_kms"]
    x = list(m["design"]["x"])
    spec = dict(m["spec"])
    s = opt.get("set")
    if s and "x" in s:
        x = list(s["x"])
    if s and "capture_period_days" in s:
        spec["capture_period_days"] = s["capture_period_days"]
    after = _maneuvers(m, x, S.MissionSpec(**spec)) if s else before
    cost = max(0.0, after - before)  # charged at the real recomputed cost, not the quoted one
    if cost > margin_kms(m) + 1e-9:
        raise ValueError("not enough propellant margin for that option")
    m["design"]["x"], m["spec"] = x, spec
    dec.update(status="decided", chosen=option_id, decided_by=by, decided_jd=jd_now, spent_kms=cost)
    redesign(m)
    for k, d in enumerate(m["decisions"]):  # requote the capture burn against the new arrival
        if d["id"] == "capture" and d["status"] != "decided":
            m["decisions"][k] = _capture_decision(m)
    m["events"] = timeline(m)
    return dec


def expire_decisions(m: dict, jd_now: float) -> list[dict]:
    """Owner stayed silent past the deadline: the probe keeps its propellant."""
    done = []
    for d in m.get("decisions", []):
        if d["status"] != "decided" and jd_now > d["deadline_jd"]:
            done.append(decide(m, d["id"], d["default"], jd_now, by="default"))
    return done


def open_decisions(m: dict, jd_now: float) -> list[dict]:
    margin = margin_kms(m)
    out = []
    for d in m.get("decisions", []):
        if d["status"] != "decided" and d["opens_jd"] <= jd_now <= d["deadline_jd"]:
            dd = dict(d)
            dd["options"] = [dict(o, affordable=o["dv_ms"] / 1000.0 <= margin + 1e-9) for o in d["options"]]
            out.append(dd)
    return out


def snapshot(m: dict, jd_now: float) -> dict:
    """Probe state right now, for the API and the in-character voice."""
    pos = position(m, jd_now)
    earth, _ = planet_state(m, "earth", jd_now)
    r = np.array(pos["r_km"])
    d_earth = float(np.linalg.norm(r - earth))
    out = {
        "phase": pos["phase"],
        "sun_distance_au": float(np.linalg.norm(r)) / AU_KM,
        "earth_distance_au": d_earth / AU_KM,
        "light_time_min": d_earth / 299792.458 / 60.0,
        "position_ecliptic_au": ecliptic_au(r),
        "propellant_margin_ms": round(margin_kms(m) * 1000, 1),
    }
    if "v_kms" in pos:
        out["heliocentric_speed_kms"] = float(np.linalg.norm(pos["v_kms"]))
    nxt = next((e for e in m["events"] if e["jd"] > jd_now), None)
    if nxt:
        out["next_event"] = {"title": nxt["title"], "date": S.iso(nxt["jd"]), "in_days": round(nxt["jd"] - jd_now, 1)}
    return out


def sky(jd: float) -> dict:
    """Planet positions and orbit polylines (ecliptic, AU) for the 3D view."""
    label = "JPL Horizons" if settings.ephemeris_source == "horizons" else "JPL DE421"
    table = _table(label, math.floor(jd) - 2, math.floor(jd) + 2)
    out = {}
    for name in PLANETS:
        r, v = table.state(name, jd)
        a = BODY[name]["a_au"] * AU_KM
        period = 2 * math.pi * math.sqrt(a**3 / MU_SUN)
        orbit = [ecliptic_au(kepler(r, v, period * k / 180, MU_SUN)[0]) for k in range(181)]
        out[name] = {"position": ecliptic_au(r), "orbit": orbit}
    return out


def target_orbit(m: dict, jd: float) -> dict | None:
    """The asteroid's orbit polyline and position (ecliptic AU) for the 3D view."""
    sb = m["spec"].get("small_body")
    if not sb:
        return None
    from app.astro import smallbody

    r, v = smallbody.state(sb, jd)
    period = 2 * math.pi * math.sqrt((sb["a"] * AU_KM) ** 3 / MU_SUN)
    orbit = [ecliptic_au(kepler(r, v, period * k / 180, MU_SUN)[0]) for k in range(181)]
    return {"name": sb["name"], "position": ecliptic_au(r), "orbit": orbit}
