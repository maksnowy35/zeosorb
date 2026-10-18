"""Values checked against the tables in the thesis (Tab. 1, 2, 8, 9)."""
import pytest

from app.core import materials, transport
from app.core.constants import P_PROCESS, T_PROCESS


@pytest.fixture
def r22():
    return materials.refrigerants()["R22"]


def test_gas_density_r22(r22):
    rho = transport.gas_density(r22.molar_mass, P_PROCESS, T_PROCESS)
    assert rho == pytest.approx(2.23, abs=0.01)


def test_henry_constant_r22_4a(r22):
    zeo = materials.zeolites()["4A"]
    rho = transport.gas_density(r22.molar_mass, P_PROCESS, T_PROCESS)
    ka, av = transport.henry_constant(1.65, zeo.bulk_density, r22.molar_mass, rho)
    assert av == pytest.approx(118.12, rel=1e-3)
    assert ka == pytest.approx(52.95, rel=5e-3)


@pytest.mark.parametrize("key, expected", [("R32", 1.69e-5), ("R22", 8.53e-6), ("R125", 5.66e-6)])
def test_molecular_diffusivity(key, expected):
    ref = materials.refrigerants()[key]
    d = transport.molecular_diffusivity(ref.molecule_size, ref.molar_mass, P_PROCESS, T_PROCESS)
    assert d == pytest.approx(expected, rel=0.02)


def test_effective_diffusivity_is_below_both(r22):
    d = transport.molecular_diffusivity(r22.molecule_size, r22.molar_mass, P_PROCESS, T_PROCESS)
    dk = transport.knudsen_diffusivity(4.0, r22.molar_mass, T_PROCESS)
    de = transport.effective_diffusivity(d, dk)
    assert de < d and de < dk


def test_every_zeolite_has_some_data():
    for z in materials.zeolites():
        assert materials.adsorption()[z], z
