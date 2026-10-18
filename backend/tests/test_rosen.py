import numpy as np
import pytest

from app.core import rosen


def test_e_for_threshold_matches_table():
    # Tab. 12 in the thesis
    assert rosen.e_for_threshold(0.5) == pytest.approx(0.0)
    assert rosen.e_for_threshold(0.024) == pytest.approx(-1.40, abs=0.01)
    assert rosen.e_for_threshold(0.920) == pytest.approx(1.00, abs=0.02)


ARGS = dict(lam=500.0, psi=0.2, d_eff=1e-7, radius=0.002, height=2.0, w=0.05)


def test_lower_threshold_means_earlier_breakthrough():
    t1 = rosen.breakthrough_time(0.01, **ARGS)
    t5 = rosen.breakthrough_time(0.05, **ARGS)
    t50 = rosen.breakthrough_time(0.5, **ARGS)
    assert t1 < t5 < t50


def test_half_concentration_at_stoichiometric_time():
    t50 = rosen.breakthrough_time(0.5, **ARGS)
    ts = rosen.stoichiometric_time(ARGS["lam"], ARGS["d_eff"], ARGS["radius"], ARGS["height"], ARGS["w"])
    assert t50 == pytest.approx(ts)


def test_curve_is_monotonic_and_bounded():
    t, c = rosen.curve(**ARGS)
    assert np.all(np.diff(t) > 0)
    assert np.all(np.diff(c) >= -1e-12)
    assert c[0] == 0.0
    assert c[-1] == pytest.approx(1.0, abs=1e-3)
