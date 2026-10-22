import numpy as np
import pytest

from app.core import isotherms, materials


@pytest.mark.parametrize("zeolite", ["4A", "5A", "13X"])
def test_anchored_to_thesis_points(zeolite):
    for ref, q in materials.adsorption()[zeolite].items():
        assert isotherms.langmuir(zeolite, ref).q(0.8, 373.15) == pytest.approx(q, rel=1e-9)


def test_loading_falls_with_temperature_and_rises_with_pressure():
    L = isotherms.langmuir("13X", "R32")
    assert L.q(1.0, 298.15) > L.q(1.0, 373.15) > L.q(1.0, 473.15)
    assert L.q(0.1, 373.15) < L.q(1.0, 373.15) < L.q_m


def test_estimates_are_flagged():
    assert isotherms.langmuir("4A", "R22").estimated


def test_competition_in_mixture():
    mix = isotherms.Mixture("13X", ["R32", "R125"])
    alone = isotherms.langmuir("13X", "R32").q(1.0, 373.15)
    both = mix.q_star(np.array([[1.0, 1.0]]), np.array([373.15]))[0]
    assert both[0] < alone
    # R32 is the stronger one on 13X
    assert both[0] / both[1] > 1


def test_capacity_curve_shape():
    c = isotherms.capacity_curve("13X", {"R32": 0.5, "R125": 0.5}, 2e5, [300.0, 400.0, 500.0])
    assert c["q_kg"].shape == (3, 2)
    assert np.all(np.diff(c["q_kg"][:, 0]) < 0)
