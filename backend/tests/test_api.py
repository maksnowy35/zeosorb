from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_materials():
    m = client.get("/api/materials").json()
    assert set(m["zeolites"]) == {"4A", "5A", "13X"}
    assert "R32" in m["refrigerants"]


def test_breakthrough_ok():
    r = client.post("/api/breakthrough", json={"refrigerant": "R22", "zeolite": "4A"})
    assert r.status_code == 200
    body = r.json()
    assert 0 < body["t_breakthrough"] < body["t_stoich"]
    assert len(body["curve"]["t"]) == len(body["curve"]["c"])


def test_breakthrough_missing_isotherm():
    r = client.post("/api/breakthrough", json={"refrigerant": "R22", "zeolite": "13X"})
    assert r.status_code == 422


def test_breakthrough_unknown_material():
    r = client.post("/api/breakthrough", json={"refrigerant": "R1234yf", "zeolite": "4A"})
    assert r.status_code == 404


def test_higher_flow_shorter_time():
    t = [
        client.post("/api/breakthrough", json={"refrigerant": "R32", "zeolite": "5A", "mass_flow": m}).json()["t_breakthrough"]
        for m in (5, 30, 100)
    ]
    assert t[0] > t[1] > t[2]


def test_matrix():
    m = client.get("/api/matrix", params={"mass_flow": 30}).json()
    assert len(m["cells"]) == len(m["zeolites"]) * len(m["refrigerants"])
    missing = [c for c in m["cells"] if c["t_breakthrough"] is None]
    assert {"zeolite": "13X", "refrigerant": "R22"} in [{k: c[k] for k in ("zeolite", "refrigerant")} for c in missing]
