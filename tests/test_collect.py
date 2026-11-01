"""Collection swarm and ranking, offline: fixture catalog, DE421 kernel, mocked HTTP."""
import asyncio
import json
from pathlib import Path

import pytest

from app.collect import agents, run
from app.prospect import rank as R

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

    monkeypatch.setattr(agents, "catalog_agent", fake_catalog)
    monkeypatch.setattr(agents, "physical_agent", fake_phys)
    monkeypatch.setattr(agents, "imagery_agent", fake_img)
    out = asyncio.run(run.collect())
    s = out["system"]
    assert len(s["planets"]) == 8 and len(s["bodies"]) == len(FIXTURE)
    row = s["bodies"][0]
    assert row["rk"]["any"] == 1 and len(row["el"]) == 7 and set(row["t"]) == set(R.RESOURCES)
    assert [a["agent"] for a in out["manifest"]["agents"]] == ["catalog", "ephemeris", "physical", "imagery"]


def test_empty_catalog_refuses_to_publish(monkeypatch):
    async def empty(*a, **k):
        return agents._result("catalog", "fixture", [], "unreachable")

    monkeypatch.setattr(agents, "catalog_agent", empty)
    with pytest.raises(SystemExit):
        asyncio.run(run.collect())


def test_imagery_match_requires_body_name():
    item = {"data": [{"title": "Bennu Sample Return Capsule", "keywords": []}]}
    assert agents._match(item, ["Bennu"]) and not agents._match(item, ["Ryugu"])
