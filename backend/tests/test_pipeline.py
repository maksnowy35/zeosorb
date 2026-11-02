import pytest

from app.core import pipeline


def run(mode, **kw):
    return pipeline.run(pipeline.BedInput(refrigerant="R22", zeolite="4A", mode=mode, **kw))


def test_thesis_mode_reproduces_tab_9():
    res = run("thesis")
    # D'(R22, 4A) = 2.7e-6 m2/s in the thesis
    assert res["diffusion"]["D_eff"] == pytest.approx(2.7e-6, rel=0.02)


def test_corrected_stoichiometric_time_is_the_mass_balance():
    # bed capacity / feed: q M rho_n V_bed / m_dot, plus the gas hold-up H/w
    res = run("corrected")
    eq, hyd = res["equilibrium"], res["hydraulics"]
    v_bed = hyd["area"] * 2.89
    t_capacity = eq["av"] * v_bed / (30.0 / 3600.0)
    assert t_capacity / 3600 == pytest.approx(2.23, abs=0.01)
    # + gas in the space between the grains and in the grains' macropores
    t_gas = hyd["t_residence"] * (1 + (1 - hyd["eps"]) / hyd["eps"] * res["diffusion"]["eps_M"])
    assert res["t_stoich"] == pytest.approx(t_capacity + t_gas, rel=1e-6)


def test_thesis_mode_misses_one_minus_eps_of_the_capacity():
    a, b = run("thesis"), run("corrected")
    gas = a["hydraulics"]["t_residence"]
    ratio = (a["t_stoich"] - gas) / (b["t_stoich"] - b["hydraulics"]["t_residence"])
    assert ratio == pytest.approx(1.0 - 0.633, rel=0.02)
    assert a["t_stoich"] / 3600 == pytest.approx(0.85, abs=0.02)


def test_tortuosity_slows_diffusion():
    for mode in ("thesis", "corrected"):
        a, b = run(mode, tortuosity=1.0), run(mode, tortuosity=3.0)
        assert b["diffusion"]["D_eff"] == pytest.approx(a["diffusion"]["D_eff"] / 3.0)
        assert b["rosen"]["lambda"] < a["rosen"]["lambda"]


def test_default_tortuosity_depends_on_mode():
    assert run("thesis")["diffusion"]["tau"] == 1.0
    assert run("corrected")["diffusion"]["tau"] == pytest.approx(2.6)


def test_pellet_model_rosen_mapping():
    # K D' = eps_M D_pore, so lambda' and psi only see the macropore transport
    res = run("corrected")
    d, bed = res["diffusion"], res["bed"]
    assert bed.ka * bed.d_eff == pytest.approx(d["eps_M"] * d["D_pore"], rel=1e-12)
    # macropores of ~0.6 um: Knudsen and bulk diffusion are of the same order (transition regime)
    assert 0.1 < d["D"] / d["DK"] < 10


def test_corrected_mode_is_slower_and_wider_than_thesis():
    a, b = run("thesis"), run("corrected")
    # thesis: Knudsen with the 1e-8 slip made the grains ~100x too fast
    assert b["bed"].ka * b["bed"].d_eff < a["bed"].ka * a["bed"].d_eff / 50
    assert b["spreading"]["sigma_rel"] > a["spreading"]["sigma_rel"]
    # ...but the bed holds more, so it breaks through later
    assert b["breakthrough"]["0.05"] > a["breakthrough"]["0.05"]


def test_spreading_budget_consistent_with_rosen():
    # without dispersion the LDF variance must equal the Rosen one, 2(1+5psi)/(5 lambda'),
    # rescaled from tau' (measured from H/w) to t (measured from 0)
    res = run("corrected")
    bed = res["bed"]
    k = bed.kappa
    rosen_var = 2 * (1 + 5 * bed.psi) / (5 * bed.lam) * (k / (1 + k)) ** 2
    assert res["spreading"]["mass_transfer"] == pytest.approx(rosen_var, rel=1e-9)


def test_audit_rows_cover_both_modes():
    from app.core import audit

    inp = pipeline.BedInput(refrigerant="R22", zeolite="4A", mode="corrected", tortuosity=4.0)
    rows = {r["symbol"]: r for r in audit.rows(inp, 0.05)}
    # thesis column = thesis mode as it is, whatever the user set in the other mode
    assert rows["τ"]["thesis"] == 1.0 and rows["τ"]["corrected"] == 4.0
    assert rows["D'"]["thesis"] == pytest.approx(2.7e-6, rel=0.02)
    assert rows["D_p"]["thesis"] is None and rows["D_p"]["corrected"] > 0
    assert rows["ε"]["thesis"] == 0.633 and rows["ε"]["corrected"] == pytest.approx(0.496, abs=0.002)
    assert rows["t_b"]["corrected"] == pytest.approx(run("corrected", tortuosity=4.0)["breakthrough"]["0.05"])
    assert all(r["thesis_source"] and r["corrected_source"] for r in rows.values())
