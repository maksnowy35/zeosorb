"""Bed structure derived from the raw numbers in thesis ch. 4."""
import pytest

from app.core import materials


@pytest.mark.parametrize("key", ["4A", "5A", "13X"])
def test_thesis_porosity_is_recovered_from_raw_data(key):
    # thesis: rho_p = m_k / (V_k - v_p m_k), eps = (rho_p - rho_n) / rho_p
    zeo = materials.zeolites()[key]
    eps = 1.0 - zeo.bulk_density / zeo.thesis_particle_density
    assert eps == pytest.approx(zeo.bed_porosity, abs=0.006)


@pytest.mark.parametrize("key", ["4A", "5A", "13X"])
def test_grain_volume_matches_radius(key):
    zeo = materials.zeolites()[key]
    sphere = 4.0 / 3.0 * 3.141592653589793 * zeo.grain_radius**3
    assert zeo.grain_volume == pytest.approx(sphere, rel=0.01)


def test_thesis_porosity_is_total_voidage():
    # (1 - eps_thesis) = (1 - eps_b)(1 - eps_micro): the thesis value counts the space
    # between the grains and the zeolite micropores together
    for zeo in materials.zeolites().values():
        total = 1.0 - (1.0 - zeo.interparticle_voidage) * (1.0 - zeo.micropore_fraction)
        assert total == pytest.approx(1.0 - zeo.bulk_density / zeo.thesis_particle_density, rel=1e-9)
        assert zeo.interparticle_voidage < zeo.bed_porosity


def test_interparticle_voidage_values():
    z = materials.zeolites()
    assert z["4A"].interparticle_voidage == pytest.approx(0.496, abs=0.002)
    assert z["5A"].interparticle_voidage == pytest.approx(0.603, abs=0.002)
    assert z["13X"].interparticle_voidage == pytest.approx(0.423, abs=0.002)
