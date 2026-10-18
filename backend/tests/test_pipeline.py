import pytest

from app.core import pipeline


def run(mode, **kw):
    return pipeline.run(pipeline.BedInput(refrigerant="R22", zeolite="4A", mode=mode, **kw))


def test_thesis_mode_reproduces_tab_9():
    res = run("thesis")
    # D'(R22, 4A) = 2.7e-6 m2/s in the thesis
    assert res["diffusion"]["D_eff"] == pytest.approx(2.7e-6, rel=0.02)


def test_stoichiometric_time_does_not_depend_on_mode():
    # t_stoich = H/w (1 + Ka/z) - pure mass balance, kinetics only change the spread
    a, b = run("thesis"), run("corrected")
    assert a["t_stoich"] == pytest.approx(b["t_stoich"], rel=1e-9)


def test_corrected_mode_gives_wider_front():
    a, b = run("thesis"), run("corrected")
    assert b["spreading"]["sigma_rel"] > a["spreading"]["sigma_rel"]
    assert b["breakthrough"]["0.05"] < a["breakthrough"]["0.05"]


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
