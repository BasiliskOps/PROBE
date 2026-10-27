"""Design pipeline, live flight, waker and decisions, end to end on the offline kernel."""
import asyncio
import copy
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import waker
from app.api.routes import apply_decision, public_view
from app.astro.search import jd_from_dt
from app.main import create_app
from app.missions import designer, flight, patch, store
from app.swarm import intent

START = datetime(2026, 10, 27, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def mars():
    mid, token = store.create("Put a probe in orbit around Mars")
    m = asyncio.run(designer.design(mid, plan="fleet", start=START))
    assert m["status"] == "ready", m.get("error")
    return mid, token


def test_intent_rules():
    a = asyncio.run(intent.parse("Send a probe to Europa that photographs Jupiter on the way"))
    assert a["target"] == "europa" and a["arrival"] == "orbit" and a["via"] == []
    b = asyncio.run(intent.parse("Fly a probe past Neptune using a Jupiter flyby"))
    assert b["target"] == "neptune" and b["arrival"] == "flyby" and b["via"] == ["jupiter"]
    c = asyncio.run(intent.parse("Land on the comet 67P"))
    assert c["supported"] is False


def test_design_is_real(mars):
    m = store.get(mars[0])
    det = m["detail"]
    assert det["sequence"] == ["earth", "mars"]
    assert jd_from_dt(START) <= det["launch_jd"] < det["arrival_jd"]
    assert 100 < det["arrival_jd"] - det["launch_jd"] < 500  # days to Mars
    assert 5 < det["c3_km2s2"] < 30
    assert m["vehicle"] and m["margin_dv_kms"] > 0
    kinds = [e["kind"] for e in m["events"]]
    assert kinds[0] == "launch" and "arrival" in kinds
    assert [e["jd"] for e in m["events"]] == sorted(e["jd"] for e in m["events"])


def test_waker_messages_once_per_milestone(mars):
    m = store.get(mars[0])
    after_arrival = datetime.fromtimestamp((m["detail"]["arrival_jd"] + 1 - 2440587.5) * 86400, tz=timezone.utc)
    sent = asyncio.run(waker.tick(after_arrival))
    assert sent >= 2
    assert asyncio.run(waker.tick(after_arrival)) == 0
    kinds = {r["kind"] for r in store.messages(mars[0])}
    assert {"designed", "launch", "arrival"} <= kinds
    assert store.get(mars[0])["status"] in ("arrived", "in_flight")


def test_capture_decision_changes_the_mission(mars):
    m = copy.deepcopy(store.get(mars[0]))
    cap = next(d for d in m["decisions"] if d["id"] == "capture")
    jd = cap["opens_jd"] + 1
    before = m["detail"]["arrival_dv_kms"]
    margin = flight.margin_kms(m)
    affordable = [o for o in cap["options"] if 0 < o["dv_ms"] / 1000 <= margin]
    if affordable:
        dec = flight.decide(m, "capture", affordable[0]["id"], jd)
        assert m["detail"]["arrival_dv_kms"] > before
        assert flight.margin_kms(m) == pytest.approx(margin - dec["spent_kms"])
    too_much = [o for o in cap["options"] if o["dv_ms"] / 1000 > flight.margin_kms(m)]
    if too_much and cap["status"] != "decided":
        with pytest.raises(ValueError):
            flight.decide(m, "capture", too_much[0]["id"], jd)


def test_decisions_need_owner_and_plan(mars):
    mid, token = mars
    with pytest.raises(HTTPException) as e:
        apply_decision(mid, "capture", "planned", "wrong-token")
    assert e.value.status_code == 403
    free_id, free_token = store.create("Send a probe to Venus")
    m = store.get(mars[0])
    m.update(id=free_id, plan="free")
    store.save(m)
    with pytest.raises(HTTPException) as e:
        apply_decision(free_id, "capture", "planned", free_token)
    assert e.value.status_code == 402


def test_public_api_and_patch(mars):
    mid, _ = mars
    client = TestClient(create_app(run_waker=False))
    v = client.get(f"/api/v1/missions/{mid}").json()
    assert v["route"] == ["earth", "mars"] and v["probe"]["name"]
    assert all("set" not in o for d in v["decisions"] for o in d["options"])
    t = client.get(f"/api/v1/missions/{mid}/track").json()
    assert len(t["track"]) > 20 and len(t["track"][0]) == 4
    ET.fromstring(patch.svg(store.get(mid)))
    assert client.get(f"/m/{mid}").status_code == 200
    assert client.get("/api/v1/sky").json()["planets"]["neptune"]["orbit"]


def test_mcp_tools_listed():
    client = TestClient(create_app(run_waker=False), base_url="http://127.0.0.1")
    with client:
        r = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        headers={"accept": "application/json, text/event-stream", "mcp-protocol-version": "2025-06-18"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"design_mission", "mission_status", "mission_decide"} <= names
