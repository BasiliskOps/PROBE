"""Prospecting: asteroid orbits, a flown asteroid mission, composition, targeting, surveys and the house fleet."""
import asyncio
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from scipy.optimize import differential_evolution, minimize

from app import waker
from app.api.routes import public_view
from app.astro import search as S
from app.astro import smallbody
from app.astro.constants import AU_KM, MU_SUN, OBLIQUITY_DEG
from app.astro.ephemeris import load_table
from app.missions import designer, flight, store
from app.prospect import catalog, composition, fleet, planner

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def jd(s):
    return S.jd_from_dt(datetime.fromisoformat(s).replace(tzinfo=timezone.utc))


def elements_from_state(r, v, epoch):
    """Classical elements (ecliptic, AU, deg) from an ICRF equatorial state, to round-trip the converter."""
    eps = math.radians(OBLIQUITY_DEG)
    rot = np.array([[1, 0, 0], [0, math.cos(eps), math.sin(eps)], [0, -math.sin(eps), math.cos(eps)]])
    r, v = rot @ r, rot @ v
    h = np.cross(r, v)
    n = np.cross([0, 0, 1], h)
    ev = ((np.dot(v, v) - MU_SUN / np.linalg.norm(r)) * r - np.dot(r, v) * v) / MU_SUN
    e = np.linalg.norm(ev)
    a = 1 / (2 / np.linalg.norm(r) - np.dot(v, v) / MU_SUN)
    i = math.degrees(math.acos(h[2] / np.linalg.norm(h)))
    om = math.degrees(math.atan2(n[1], n[0])) % 360
    w = math.degrees(math.atan2(np.dot(np.cross(n, ev), h) / np.linalg.norm(h), np.dot(n, ev))) % 360
    nu = math.atan2(np.dot(np.cross(ev, r), h) / np.linalg.norm(h), np.dot(ev, r))
    E = 2 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu / 2))
    M = math.degrees(E - e * math.sin(E)) % 360
    return {"a": a / AU_KM, "e": e, "i": i, "om": om, "w": w, "ma": M, "epoch": epoch}


def test_elements_round_trip_and_propagation():
    t = load_table(jd("2027-01-01"), jd("2027-08-01"), source="de421")
    r, v = t.state("mars", jd("2027-01-01"))
    el = elements_from_state(r, v, jd("2027-01-01"))
    r2, v2, _ = smallbody.state_at_epoch(el)
    assert np.linalg.norm(r2 - r) < 1.0 and np.linalg.norm(v2 - v) < 1e-6
    later, _ = smallbody.state(el, jd("2027-07-01"))
    truth, _ = t.state("mars", jd("2027-07-01"))
    assert np.linalg.norm(later - truth) < 1e5  # two-body vs DE421 over six months


def test_rediscovers_osiris_rex():
    """OSIRIS-REx: launched 2016-09-08, Earth flyby 2017-09-22, arrived at Bennu 2018-12-03."""
    bennu = catalog.find("Bennu")
    t = smallbody.extend(load_table(jd("2016-08-01"), jd("2019-06-01"), source="de421"), bennu)
    k = smallbody.key(bennu)
    spec = S.MissionSpec(target=k, small_body=bennu, dry_mass_kg=880)
    seq = ["earth", "earth", k]
    f = S.Objective(seq, t, spec)
    b = S.design_bounds(seq, jd("2016-09-08"), jd("2016-10-12"))
    b[5], b[9] = (330, 420), (380, 480)
    r = differential_evolution(f, b, popsize=15, maxiter=400, tol=1e-10, seed=2, polish=False, init="sobol",
                               mutation=(0.5, 1.0), recombination=0.9, updating="deferred")
    loc = minimize(f, r.x, method="Powell", bounds=b, options={"maxfev": 6000})
    d = S.evaluate_design(seq, loc.x if loc.fun < r.fun else r.x, t, spec)["detail"]
    assert abs(d["flybys"][0]["jd"] - jd("2017-09-22")) < 10
    assert abs(d["arrival_jd"] - jd("2018-12-03")) < 60
    assert d["dsm_dv_kms"] + d["arrival_dv_kms"] < 1.2


def test_composition_groups_and_surveys():
    assert composition.group_of("Cg", None)[0] == "carbonaceous"
    assert composition.group_of("M", 0.13)[0] == "metallic"
    assert composition.group_of("Xk", 0.05)[0] == "primitive"
    assert composition.group_of(None, 0.04)[0] == "carbonaceous"
    ryugu, psyche = catalog.find("Ryugu"), catalog.find("Psyche")
    assert composition.prior(ryugu)["fractions"]["water"] > 10 * composition.prior(psyche)["fractions"]["water"]
    assert composition.prior(psyche)["fractions"]["metal"] > 0.3
    a = composition.survey(ryugu, "rendezvous", "p1")
    assert a == composition.survey(ryugu, "rendezvous", "p1")  # deterministic per probe
    b = composition.survey(ryugu, "flyby", "p2")
    assert a["sigma"] < b["sigma"]
    c = composition.combine([a, b])
    assert c["surveys"] == 2 and c["relative_uncertainty"] < a["sigma"]
    tw = composition.truth(ryugu)["fractions"]["water"]
    assert abs(math.log(a["fractions"]["water"] / tw)) < 0.5  # rendezvous lands near the hidden truth


def test_planner_matches_resource():
    water = planner.candidates("water", "near-earth", 2)
    assert all(composition.prior(t)["group"] == "carbonaceous" for t in water)
    assert planner.reach_dv_kms(catalog.find("Amun")) > planner.reach_dv_kms(catalog.find("Itokawa"))


def test_prospecting_mission_surveys_at_mission_time():
    mid, _ = store.create("Find water on a near-Earth asteroid")
    m = asyncio.run(designer.design(mid, plan="fleet", start=NOW))
    assert m["status"] == "ready", m.get("error")
    assert composition.prior(m["target"])["group"] == "carbonaceous"
    kinds = [e["kind"] for e in m["events"]]
    assert "survey" in kinds and kinds.index("survey") > kinds.index("arrival")
    survey_jd = next(e["jd"] for e in m["events"] if e["kind"] == "survey")
    real_days = (survey_jd - m["clock"]["sim0"]) / m["clock"]["rate"]
    assert real_days < 120  # the mission clock turns years of flight into weeks
    before = NOW + timedelta(days=real_days - 1)
    asyncio.run(waker.tick(before, fleet_enabled=False))
    assert public_view(store.get(mid), S.jd_from_dt(before))["findings"] is None
    after = NOW + timedelta(days=real_days + 1)
    asyncio.run(waker.tick(after, fleet_enabled=False))
    v = public_view(store.get(mid), S.jd_from_dt(after))
    assert v["findings"]["mode"] == "rendezvous" and v["findings"]["tonnes"]["water"] > 0
    assert v["atlas"]["surveys"] == 1
    assert any(r["kind"] == "survey" for r in store.messages(mid))


def test_house_fleet_launches_once_a_day(monkeypatch):
    didymos = catalog.find("Didymos")
    monkeypatch.setattr(catalog, "new_neos", lambda *a, **k: [didymos])
    day = NOW + timedelta(days=3)
    launched = asyncio.run(fleet.run_daily(day))
    assert len(launched) == 1
    m = store.get(launched[0])
    assert m["plan"] == "house" and m["target"]["id"] == didymos["id"]
    assert asyncio.run(fleet.run_daily(day + timedelta(hours=2))) == []
