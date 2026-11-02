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
    assert res["t_stoich"] == pytest.approx(t_capacity + hyd["t_residence"], rel=1e-6)


def test_thesis_mode_misses_one_minus_eps_of_the_capacity():
    a, b = run("thesis"), run("corrected")
    gas = a["hydraulics"]["t_residence"]
    ratio = (a["t_stoich"] - gas) / (b["t_stoich"] - b["hydraulics"]["t_residence"])
    assert ratio == pytest.approx(1.0 - 0.633, rel=0.01)
    assert a["t_stoich"] / 3600 == pytest.approx(0.85, abs=0.02)


def test_tortuosity_slows_diffusion():
    a, b = run("corrected"), run("corrected", tortuosity=3.0)
    assert b["diffusion"]["D_eff"] == pytest.approx(a["diffusion"]["D_eff"] / 3.0)
    assert b["rosen"]["lambda"] < a["rosen"]["lambda"]


def test_spreading_budget_consistent_with_rosen():
    # without dispersion the LDF variance must equal the Rosen one, 2(1+5psi)/(5 lambda'),
    # rescaled from tau' (measured from H/w) to t (measured from 0)
    res = run("corrected")
    bed = res["bed"]
    k = bed.kappa
    rosen_var = 2 * (1 + 5 * bed.psi) / (5 * bed.lam) * (k / (1 + k)) ** 2
    assert res["spreading"]["mass_transfer"] == pytest.approx(rosen_var, rel=1e-9)
