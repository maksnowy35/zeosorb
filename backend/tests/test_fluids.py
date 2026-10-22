import pytest

from app.core import fluids


def test_saturation_pressure_r32():
    # R32 at 20 C: 14.75 bar (NIST)
    assert fluids.fluid("R32").p_sat(293.15) == pytest.approx(14.75e5, rel=0.01)


def test_two_phase_state():
    fl = fluids.fluid("R410A")
    s = fl.sat_p(2.5e5)
    st = fl.ph(2.5e5, s.h_l + 0.4 * s.h_fg)
    assert st.phase == "two-phase"
    assert st.x == pytest.approx(0.4)
    assert st.T == pytest.approx(s.T)


def test_superheated_vapour_properties_at_thesis_point():
    # thesis Tab. 1 used CoolProp viscosity at 100 C and 0.8 bar
    st = fluids.fluid("R22").pt(0.8e5, 373.15)
    assert st.phase == "vapour"
    assert st.mu == pytest.approx(1.72e-5, rel=0.02)
    assert st.superheat > 100


def test_transport_fallback_near_saturation():
    # R32 vapour conductivity fails exactly on the saturation line at low pressure in CoolProp
    s = fluids.fluid("R32").sat_p(fluids.P_ATM)
    assert 0.005 < s.k_v < 0.02


def test_blend_fractionation_direction():
    # R407C: the vapour above the liquid is richer in R32 (most volatile) than the liquid
    b = fluids.blend(("R32", "R125", "R134a"))
    res = b.bubble(293.15, fluids.components("R407C"))
    assert res["vapour"]["R32"] > 0.23
    assert res["vapour"]["R134a"] < 0.52


def test_mass_mole_roundtrip():
    w = fluids.components("R410A")
    back = fluids.mole_to_mass(fluids.mass_to_mole(w))
    assert back["R32"] == pytest.approx(0.5)
