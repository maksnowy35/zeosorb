import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API = "/api/v1"


def post(path, **body):
    return client.post(f"{API}{path}", json=body)


def test_health():
    assert client.get(f"{API}/health").json()["status"] == "ok"


def test_materials():
    m = client.get(f"{API}/materials").json()
    assert set(m["zeolites"]) == {"4A", "5A", "13X"}
    assert m["blends"]["R410A"] == {"R32": 50, "R125": 50}


def test_breakthrough_rosen_only():
    r = post("/breakthrough", refrigerant="R22", zeolite="4A", model="rosen")
    assert r.status_code == 200
    body = r.json()
    assert 0 < body["t_breakthrough"]["rosen"] < body["t_stoich"]
    assert body["curves"]["ldf"] is None and body["profiles"] is None


def test_breakthrough_both_models_agree_roughly():
    body = post("/breakthrough", refrigerant="R22", zeolite="4A", model="both").json()
    t = body["t_breakthrough"]
    assert t["ldf"] == pytest.approx(t["rosen"], rel=0.05)
    prof = body["profiles"]
    assert len(prof["c"]) == len(prof["t"]) and len(prof["c"][0]) == len(prof["zeta"])


def test_materials_have_derived_structure():
    z = client.get(f"{API}/materials").json()["zeolites"]["4A"]
    assert z["interparticle_voidage"] == pytest.approx(0.496, abs=0.002)
    assert z["bed_porosity"] == 0.633


def test_tortuosity_defaults_per_mode():
    c = post("/breakthrough", refrigerant="R22", zeolite="4A", model="rosen").json()
    t = post("/breakthrough", refrigerant="R22", zeolite="4A", model="rosen", mode="thesis").json()
    assert c["diffusion"]["tau"] == pytest.approx(2.6) and t["diffusion"]["tau"] == 1.0
    x = post("/breakthrough", refrigerant="R22", zeolite="4A", model="rosen", tortuosity=4.0).json()
    assert x["diffusion"]["tau"] == 4.0
    assert post("/breakthrough", refrigerant="R22", zeolite="4A", tortuosity=0.5).status_code == 422


def test_breakthrough_missing_isotherm():
    assert post("/breakthrough", refrigerant="R22", zeolite="13X").status_code == 422


def test_breakthrough_unknown_material():
    assert post("/breakthrough", refrigerant="R1234yf", zeolite="4A").status_code == 404


def test_validation():
    assert post("/breakthrough", refrigerant="R22", zeolite="4A", mass_flow=-1).status_code == 422
    assert post("/breakthrough", refrigerant="R22", zeolite="4A", mode="excel").status_code == 422


def test_matrix():
    m = client.get(f"{API}/matrix", params={"mass_flow": 30, "mode": "thesis"}).json()
    assert len(m["cells"]) == len(m["zeolites"]) * len(m["refrigerants"])
    missing = {(c["zeolite"], c["refrigerant"]) for c in m["cells"] if c["t_breakthrough"] is None}
    assert ("13X", "R22") in missing


def test_separation_r410a_on_4a():
    body = post("/separation", zeolite="4A", refrigerant_a="R32", refrigerant_b="R125").json()
    res = body["result"]
    # R125 has the lower Henry constant on 4A -> leaves first
    assert res["weak"] == "R125" and res["strong"] == "R32"
    assert res["alpha"] > 1
    assert res["window"] == pytest.approx(res["t_strong_break"] - res["t_weak_full"])
    assert {o["zeolite"] for o in body["ranking"]} == {"4A", "5A", "13X"}
    assert set(body["curves"]) == {"R32", "R125"}


def test_separation_same_refrigerant():
    assert post("/separation", zeolite="4A", refrigerant_a="R32", refrigerant_b="R32").status_code == 422


def test_sweep_mass_flow():
    body = post("/sweep", refrigerant="R32", zeolite="5A", parameter="mass_flow", start=5, stop=100, n=10).json()
    t = body["t_breakthrough"]
    assert len(t) == 10
    assert all(a > b for a, b in zip(t, t[1:]))     # more flow -> shorter time


def test_sweep_bed_height_linear_capacity():
    body = post("/sweep", refrigerant="R32", zeolite="5A", parameter="bed_height", start=1, stop=4, n=4).json()
    ts = body["t_stoich"]
    assert ts[-1] / ts[0] == pytest.approx(4.0, rel=1e-6)   # t_stoich ~ H


def test_separation_uses_blend_velocity():
    # same gas velocity for both components -> the order follows the Henry constants
    body = post("/separation", zeolite="5A", refrigerant_a="R32", refrigerant_b="R125", fraction_a=0.5).json()
    res = body["result"]
    assert res["weak"] == "R125"
    assert res["window"] > 0
