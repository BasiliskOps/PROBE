"""Collection swarm and ranking, offline: fixture catalog, DE421 kernel, mocked HTTP."""
import asyncio
import json
from pathlib import Path

import pytest

from app.collect import agents, run
from app.prospect import rank as R

MARS = """
 Revised: Sept 22, 2025                 Mars                              499
 PHYSICAL DATA (updated 2025-Sep-22):
  Vol. mean radius (km) = 3389.92+-0.04   Density (g/cm^3)      =  3.933(5+-4)
  Mass x10^23 (kg)      =    6.4171       Flattening, f         =  1/169.779
  Volume (x10^10 km^3)  =   16.318        Equatorial radius (km)=  3396.19
  Sidereal rot. period  =  24.622962 hr   Sid. rot. rate, rad/s =  0.0000708822
  Equ. gravity  m/s^2   =    3.71         Escape velocity, km/s =  5.03
  Geometric Albedo      =    0.150        Mean temperature (K)  =  210
"""
PHOBOS = """
 Revised: Sep 28, 2012             Phobos / (Mars)                     401
 SATELLITE PHYSICAL PROPERTIES:
  Radius (km)             = 13.0x11.4x9.1  Density (g cm^-3)   =  1.876 +- 0.020
  Mass (10^19 kg)         = 1.0659 +- 0.0004  Geometric Albedo    =  0.071 +- 0.012
*******************************************************************************
$$SOE
2461347.500000000 = A.D. 2026-Nov-03 00:00:00.0000 TDB
 EC= 1.566536048617082E-02 QR= 9.229744452318245E+03 IN= 2.637146028131017E+01
 OM= 8.208431020104519E+01 W = 1.505843702848834E+02 Tp=  2461347.402173118
 N = 1.128427591452993E+03 MA= 1.103073598542004E+02 TA= 1.120768128290564E+02
 A = 9.376640000613060E+03 AD= 9.523535548907875E+03 PR= 3.190281048108934E-01
$$EOE
"""

FIXTURE = json.loads((Path(__file__).parents[1] / "app" / "prospect" / "fixture_sbdb.json").read_text())


def test_ephemeris_agent_recovers_known_orbits():
    res = asyncio.run(agents.ephemeris_agent(2461345.5))  # 2026-11-01
    assert res["error"] is None and len(res["records"]) == 8
    p = {r["id"]: r for r in res["records"]}
    assert p["earth"]["a"] == pytest.approx(1.0, abs=0.002)
    assert p["earth"]["e"] == pytest.approx(0.0167, abs=0.002)
    assert p["earth"]["i"] < 0.01  # ecliptic frame
    assert p["mars"]["a"] == pytest.approx(1.524, abs=0.01)
    assert p["mars"]["i"] == pytest.approx(1.85, abs=0.05)
    assert p["jupiter"]["a"] == pytest.approx(5.20, abs=0.05)


def test_ranking_is_deterministic_and_complete():
    a, b = R.rank(FIXTURE), R.rank(list(reversed(FIXTURE)))
    assert [r["id"] for r in a] == [r["id"] for r in b]
    for key in R.RESOURCES + ["any"]:
        assert sorted(r["ranks"][key] for r in a) == list(range(1, len(a) + 1))
    for r in a:
        for k, (lo, hi) in r["assessment"]["bounds"].items():
            assert lo <= r["assessment"]["tonnes"][k] <= hi


def test_measured_parameters_replace_catalog_values():
    bennu = next(t for t in FIXTURE if t["id"] == "101955")
    phys = {"GM": {"value": "4.892e-09", "ref": "Lauretta et al. 2019"},
            "density": {"value": "1.19", "ref": "Lauretta et al. 2019"},
            "diameter": {"value": "0.4828", "ref": "Barnouin et al. 2019"}}
    t = run.apply_measured(bennu, phys)
    assert t["mass_kg"] == pytest.approx(7.33e10, rel=0.01)
    assert t["diameter_km"] == pytest.approx(0.4828)
    assert set(t["measured"]) == {"mass", "density", "diameter"}
    assert t["measured"]["mass"]["ref"] == "Lauretta et al. 2019"


def test_full_run_offline(monkeypatch):
    async def fake_catalog(*a, **k):
        return agents._result("catalog", "fixture", FIXTURE)

    async def fake_phys(ids, *a, **k):
        return agents._result("physical", "fixture", {})

    async def fake_img(bodies, *a, **k):
        return agents._result("imagery", "fixture", {})

    async def fake_hz(jd, *a, **k):
        moon = {"id": "phobos", "name": "Phobos", "parent": "mars", "hid": "401", **agents.parse_elements(PHOBOS),
                "phys": agents.parse_object_data(PHOBOS)}
        return agents._result("horizons", "fixture", {"moons": [moon], "planet_phys": {"mars": agents.parse_object_data(MARS)}})

    monkeypatch.setattr(agents, "catalog_agent", fake_catalog)
    monkeypatch.setattr(agents, "physical_agent", fake_phys)
    monkeypatch.setattr(agents, "imagery_agent", fake_img)
    monkeypatch.setattr(agents, "horizons_agent", fake_hz)
    out = asyncio.run(run.collect())
    s = out["system"]
    assert len(s["planets"]) == 8 and len(s["bodies"]) == len(FIXTURE)
    row = s["bodies"][0]
    assert row["rk"]["any"] == 1 and len(row["el"]) == 7 and set(row["t"]) == set(R.RESOURCES)
    assert [a["agent"] for a in out["manifest"]["agents"]] == ["catalog", "ephemeris", "horizons", "physical", "imagery"]
    assert s["moons"][0]["parent"] == "mars"
    mars = next(p for p in s["planets"] if p["id"] == "mars")
    assert mars["phys"]["radius_km"] == pytest.approx(3389.92)


def test_empty_catalog_refuses_to_publish(monkeypatch):
    async def empty(*a, **k):
        return agents._result("catalog", "fixture", [], "unreachable")

    async def no_hz(jd, *a, **k):
        return agents._result("horizons", "fixture", {"moons": [], "planet_phys": {}})

    monkeypatch.setattr(agents, "catalog_agent", empty)
    monkeypatch.setattr(agents, "horizons_agent", no_hz)
    with pytest.raises(SystemExit):
        asyncio.run(run.collect())


def test_imagery_match_requires_body_name():
    item = {"data": [{"title": "Bennu Sample Return Capsule", "keywords": []}]}
    assert agents._match(item, ["Bennu"]) and not agents._match(item, ["Ryugu"])


def test_horizons_elements_and_physical_data_parse():
    el = agents.parse_elements(PHOBOS)
    assert el["epoch"] == pytest.approx(2461347.5)
    assert el["a_km"] == pytest.approx(9376.64, rel=1e-6)
    assert el["e"] == pytest.approx(0.015665, rel=1e-4)
    assert el["w"] == pytest.approx(150.584, rel=1e-5) and el["n"] == pytest.approx(1128.4276, rel=1e-6)
    assert el["period_d"] == pytest.approx(0.319028, rel=1e-5)
    mars = agents.parse_object_data(MARS)
    assert mars["radius_km"] == pytest.approx(3389.92)
    assert mars["mass_kg"] == pytest.approx(6.4171e23)
    assert mars["density"] == pytest.approx(3.933)
    assert mars["rotation_h"] == pytest.approx(24.622962)
    assert mars["gravity"] == pytest.approx(3.71) and mars["escape"] == pytest.approx(5.03)
    assert mars["albedo"] == pytest.approx(0.150)
    pho = agents.parse_object_data(PHOBOS)
    assert pho["radius_km"] == pytest.approx(13.0) and pho["density"] == pytest.approx(1.876)
    assert pho["mass_kg"] == pytest.approx(1.0659e19)
    assert agents.parse_elements("no ephemeris here") is None
