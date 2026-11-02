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


def test_knudsen_r22_4a():
    # DK = dp/3 sqrt(8RT/(pi M)) with dp = 4 A = 4e-10 m
    dk = transport.knudsen_diffusivity(4.0, 86.47, T_PROCESS)
    assert dk == pytest.approx(4.03e-8, rel=0.01)


def test_knudsen_thesis_scale_reproduces_tab_8():
    # thesis Tab. 8: DK(R22, 4A) = 4.0e-6 (pore diameter converted with 1e-8)
    dk = transport.knudsen_diffusivity(4.0, 86.47, T_PROCESS, scale=transport.THESIS_PORE_SCALE)
    assert dk == pytest.approx(4.0e-6, rel=0.02)


@pytest.mark.parametrize("key, thesis_value", [("R32", 1.69e-5), ("R22", 8.53e-6), ("R125", 5.66e-6)])
def test_chapman_enskog_close_to_kinetic_theory(key, thesis_value):
    # D = 1.32 mu / rho from the viscosity should land within ~20 % of the thesis values
    ref = materials.refrigerants()[key]
    rho = transport.gas_density(ref.molar_mass, P_PROCESS, T_PROCESS)
    d = transport.self_diffusivity(ref.viscosity, rho)
    assert d == pytest.approx(thesis_value, rel=0.25)


def test_knudsen_in_macropores():
    # 0.59 um macropores: DK ~ 6e-5 m2/s, three orders above the (unphysical) window value
    dk = transport.knudsen_diffusivity(5.9e-7, 86.47, T_PROCESS, scale=transport.METRE)
    assert dk == pytest.approx(5.9e-5, rel=0.02)


def test_wakao_funazkri_limit():
    assert transport.sherwood_wakao_funazkri(0.0, 1.0) == pytest.approx(2.0)


def test_effective_diffusivity_is_below_both(r22):
    d = transport.molecular_diffusivity(r22.molecule_size, r22.molar_mass, P_PROCESS, T_PROCESS)
    dk = transport.knudsen_diffusivity(4.0, r22.molar_mass, T_PROCESS)
    de = transport.effective_diffusivity(d, dk)
    assert de < d and de < dk


def test_every_zeolite_has_some_data():
    for z in materials.zeolites():
        assert materials.adsorption()[z], z
