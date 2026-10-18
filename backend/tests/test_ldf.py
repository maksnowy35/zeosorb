"""The numerical model has to agree with the Rosen solution where both are valid."""
import math

import numpy as np
import pytest

from app.core import ldf, pipeline, rosen


def rosen_theta(threshold, lam, psi, kappa):
    """Rosen breakthrough in theta = t w / H units."""
    s = math.sqrt((1 + 5 * psi) / (5 * lam))
    return 1 + kappa * (1 + 2 * rosen.e_for_threshold(threshold) * s)


@pytest.fixture(scope="module")
def no_dispersion():
    lam, psi, kappa = 100.0, 0.1, 30.0
    st = 5 * lam / (kappa * (1 + 5 * psi))     # same k_LDF as pipeline.Bed.k_ldf
    sol = ldf.solve(kappa=kappa, stanton=st, peclet=1e7, t_ref=1.0, t_end=1.6 * (1 + kappa))
    return sol, lam, psi, kappa


@pytest.mark.parametrize("threshold", [0.05, 0.5, 0.95])
def test_matches_rosen_without_dispersion(no_dispersion, threshold):
    sol, lam, psi, kappa = no_dispersion
    assert sol.time_at(threshold) == pytest.approx(rosen_theta(threshold, lam, psi, kappa), rel=0.015)


def test_mass_balance(no_dispersion):
    sol, *_ , kappa = no_dispersion
    adsorbed = np.trapezoid(1.0 - sol.c_out, sol.t)          # in units of c0 * bed volume / (w A)
    assert adsorbed == pytest.approx(1 + kappa, rel=0.01)


def test_profiles_are_bounded_and_ordered(no_dispersion):
    sol, *_ = no_dispersion
    assert sol.c_profiles.shape == (len(sol.t_profiles), len(sol.zeta))
    assert sol.c_profiles.min() >= 0 and sol.q_profiles.max() <= 1
    mid = len(sol.t_profiles) // 2
    # front moves from inlet to outlet: inlet more loaded than outlet
    assert sol.q_profiles[mid, 0] > sol.q_profiles[mid, -1]


def test_dispersion_widens_front():
    res = pipeline.run(pipeline.BedInput("R22", "4A", mode="thesis", thresholds=(0.05,)))
    sol = ldf.simulate(res["bed"])
    # in thesis mode the front is so sharp that axial dispersion dominates -> LDF breaks through earlier
    assert sol.time_at(0.05) < res["breakthrough"]["0.05"]
    assert sol.time_at(0.5) == pytest.approx(res["t_stoich"], rel=0.01)
