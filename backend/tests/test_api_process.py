import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API = "/api/v1"


@pytest.fixture(scope="module")
def defaults():
    return client.get(f"{API}/process/defaults").json()


def test_defaults(defaults):
    assert defaults["feed"]["segments"][0]["D_mm"] == 40
    assert defaults["feed"]["segments"][1]["D_mm"] == 90
    assert "two_bed_10_step" in defaults["presets"]


def test_feed_default_line():
    b = client.post(f"{API}/feed", json={}).json()
    assert b["outlet"]["phase"] == "vapour"
    z = b["line"]["z"]
    assert z[0] == 0 and z[-1] == pytest.approx(5.0)
    assert len(b["segments"]) == 2
    assert b["tank"]["t_h"][-1] == pytest.approx(8.0, rel=1e-3)
    assert b["capacity"]["min_safe_C"] == pytest.approx(b["capacity"]["dew_C"] + 10, abs=0.01)
    assert any("Viscosity" in f["text"] for f in b["findings"])


def test_feed_liquid_withdrawal_evaporates():
    b = client.post(f"{API}/feed", json={"tank": {"withdrawal": "liquid"}}).json()
    assert b["reducer"]["phase_out"] == "two-phase"
    assert b["segments"][0]["duty_W"] > 1000


def test_feed_solve_hits_target():
    b = client.post(f"{API}/feed/solve", json={"segment": 0, "target_C": 80}).json()
    assert b["solved"]["reached"]
    assert b["outlet"]["T_C"] == pytest.approx(80, abs=0.5)
    assert b["segments"][0]["T_out_C"] > b["segments"][0]["T_in_C"]


def test_feed_solve_rejects_insulated_segment():
    body = {"segment": 0, "segments": [{"name": "s", "D_mm": 40, "L_m": 3, "heating": {"kind": "insulated"}}]}
    assert client.post(f"{API}/feed/solve", json=body).status_code == 422


def test_feed_unknown_fluid():
    assert client.post(f"{API}/feed", json={"fluid": "R1234yf"}).status_code == 404


def test_cycle_short_run(defaults):
    steps = defaults["presets"]["vsa_4_step"]["steps"]
    r = client.post(f"{API}/cycle", json={"steps": steps, "max_cycles": 2, "bed": {"cells": 8}})
    assert r.status_code == 200
    b = r.json()
    assert len(b["steps"]) == 4
    assert -1.0 < min(b["series"]["A"]["P"]) < 0          # bar g, evacuated
    assert 50 < b["series"]["A"]["T_mid"][-1] < 300        # °C
    assert b["cycles"] == 2


def test_cycle_rejects_missing_isotherm(defaults):
    steps = defaults["presets"]["vsa_4_step"]["steps"]
    r = client.post(f"{API}/cycle", json={"steps": steps, "plant": {"feed": "R22"}})
    assert r.status_code == 422
    assert "R22" in r.json()["detail"]
