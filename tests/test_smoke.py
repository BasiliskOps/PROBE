from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index():
    assert client.get("/").status_code == 200


def test_design_requires_payment():
    r = client.post("/api/v1/missions/design", json={"sentence": "send a probe to Europa"})
    assert r.status_code == 402


def test_status_is_free():
    assert client.get("/api/v1/missions/abc").status_code == 501
