"""Engine checks against JPL data and a flown mission (Europa Clipper)."""
from datetime import datetime, timezone

import numpy as np
import pytest
from scipy.optimize import differential_evolution, minimize

from app.astro import search as S
from app.astro import vehicles
from app.astro.constants import AU_KM, MU_SUN
from app.astro.ephemeris import load_table, parse_horizons_vectors
from app.astro.mga import hermite, kepler


def jd(s):
    return S.jd_from_dt(datetime.fromisoformat(s).replace(tzinfo=timezone.utc))


@pytest.fixture(scope="module")
def table():
    return load_table(jd("2024-09-01"), jd("2031-06-01"), source="de421")


def test_interpolation_matches_de421(table):
    import de421
    from jplephem import Ephemeris

    e = Ephemeris(de421)
    t = jd("2027-03-14") + 0.37
    r, v = table.state("jupiter", t)
    p, vv = e.position_and_velocity("jupiter", t)
    sp, sv = e.position_and_velocity("sun", t)
    assert np.linalg.norm(r - (p - sp).ravel()) < 1.0  # km
    assert np.linalg.norm(v - ((vv - sv).ravel() / 86400.0)) < 1e-6
    r, _ = table.state("earth", t)
    assert 0.98 < np.linalg.norm(r) / AU_KM < 1.02


def test_horizons_parser():
    text = (
        "header\n$$SOE\n"
        "2461340.500000000, A.D. 2026-Oct-27 00:00:00.0000,  1.0E+08,  2.0E+07, -3.0E+06,"
        "  1.1E+01, -2.0E+01,  5.0E-01,\n"
        "2461341.500000000, A.D. 2026-Oct-28 00:00:00.0000,  1.1E+08,  2.1E+07, -3.1E+06,"
        "  1.2E+01, -2.1E+01,  5.1E-01,\n"
        "$$EOE\nfooter"
    )
    rows = parse_horizons_vectors(text)
    assert rows.shape == (2, 7)
    assert rows[0, 0] == 2461340.5 and rows[1, 1] == 1.1e8 and rows[1, 6] == 0.51


def test_kepler_round_trip(table):
    r0, v0 = table.state("mars", jd("2027-01-01"))
    r1, v1 = kepler(r0, v0, 200 * 86400.0, MU_SUN)
    r2, v2 = kepler(r1, v1, -200 * 86400.0, MU_SUN)
    assert np.linalg.norm(r2 - r0) < 1e-2
    truth, _ = table.state("mars", jd("2027-01-01") + 200)
    assert np.linalg.norm(r1 - truth) < 2e5  # two-body vs full ephemeris over 200 days


def test_vehicle_catalog():
    assert vehicles.capacity_kg(vehicles.VEHICLES[-1], 10) == 12345
    assert vehicles.capacity_kg(vehicles.VEHICLES[-1], 80) == 0.0  # never extrapolated
    assert vehicles.select_vehicle(20.0, 2000.0)["name"] == "New Glenn"
    lv = vehicles.select_vehicle(20.0, 2400.0)
    assert lv["name"] == "Falcon Heavy (recoverable)"
    assert vehicles.select_vehicle(54.0, 9000.0) is None


def test_rediscovers_europa_clipper(table):
    """Inside Clipper's real launch period the optimizer finds Clipper's trajectory.

    Flown: launch 2024-10-14 on Falcon Heavy expendable, Mars flyby 2025-03-01 at
    884 km, Earth flyby 2026-12-03, Jupiter 2030-04, orbit insertion ~840 m/s.
    """
    seq = ["earth", "mars", "earth", "jupiter"]
    spec = S.MissionSpec(target="europa", dry_mass_kg=3241)
    f = S.Objective(seq, table, spec)
    b = S.design_bounds(seq, jd("2024-10-10"), jd("2024-10-24"))
    b[5], b[9], b[13] = (120, 150), (600, 700), (1180, 1260)
    r = differential_evolution(f, b, popsize=15, maxiter=400, tol=1e-10, seed=1, polish=False, init="sobol",
                               mutation=(0.5, 1.0), recombination=0.9, updating="deferred")
    loc = minimize(f, r.x, method="Powell", bounds=b, options={"maxfev": 6000})
    x = loc.x if loc.fun < r.fun else r.x
    d = S.evaluate_design(seq, x, table, spec)
    det = d["detail"]
    mars, earth = det["flybys"]
    assert abs(mars["jd"] - jd("2025-03-01")) < 5 and 600 < mars["altitude_km"] < 1200
    assert abs(earth["jd"] - jd("2026-12-03")) < 5
    assert 0.8 < det["arrival_dv_kms"] < 1.0
    assert d["vehicle"]["name"] == "Falcon Heavy (expendable)"


def test_decoded_arcs_are_continuous(table):
    seq = ["earth", "mars", "earth", "jupiter"]
    spec = S.MissionSpec(target="jupiter")
    x = [jd("2024-10-18"), 0.3, 0.3, 6.0, 0.1, 135.0, 0.5, 2.0, 0.5, 640.0, 0.0, 3.0, 0.5, 1220.0]
    d = S.evaluate_design(seq, x, table, spec)["detail"]
    for arc in d["arcs"][1::2]:  # post-DSM Lambert arcs must end on the target planet
        r_end, _ = kepler(np.array(arc["r0_km"]), np.array(arc["v0_kms"]),
                          (arc["jd_end"] - arc["jd_start"]) * 86400.0, MU_SUN)
        r_planet, _ = table.state(arc["to"], arc["jd_end"])
        assert np.linalg.norm(r_end - r_planet) < 50.0
