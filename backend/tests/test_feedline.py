import pytest

from app.core import feedline as fl, fluids, tank


def segments(kind1="medium", kind2="medium", T1=363.15, T2=373.15):
    return [
        fl.Segment("Segment 1", 0.04, 3.0, heating=fl.Heating(kind=kind1, T_medium=T1)),
        fl.Segment("Segment 2", 0.09, 2.0, heating=fl.Heating(kind=kind2, T_medium=T2)),
    ]


@pytest.fixture(scope="module")
def sat():
    return fluids.fluid("R410A").sat_T(293.15)


def test_reducer_is_isenthalpic_and_cools(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_v, 2.5e5, segments("insulated", "insulated"))
    assert r.h[0] == pytest.approx(sat.h_v, rel=1e-9)
    assert r.reducer["T_out"] < 273.15          # Joule-Thomson: saturated vapour at 20 C -> below 0 C


def test_energy_balance_closes(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_l, 2.5e5, segments())
    duty = sum(s.duty for s in r.segments)
    assert duty == pytest.approx(30 / 3600 * (r.h[-1] - r.h[0]), rel=1e-6)


def test_liquid_feed_is_evaporated_in_segment_1(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_l, 2.5e5, segments())
    assert r.reducer["phase_out"] == "two-phase"
    assert r.segments[0].x_out is None and r.outlet.phase == "vapour"
    # evaporation needs far more heat than superheating
    assert r.segments[0].duty > 5 * r.segments[1].duty


def test_long_heated_pipe_approaches_medium_temperature(sat):
    segs = [fl.Segment("long", 0.04, 60.0, heating=fl.Heating(kind="medium", T_medium=353.15))]
    r = fl.simulate("R410A", 10, sat.p, sat.h_v, 2.5e5, segs)
    assert r.outlet.T == pytest.approx(353.15, abs=0.5)


def test_pressure_drop_is_small_but_positive(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_v, 2.5e5, segments())
    assert 0 < r.p[0] - r.p[-1] < 500


def test_wide_pipe_has_low_coefficient(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_v, 2.5e5, segments())
    assert r.segments[1].h_mean < r.segments[0].h_mean


def test_cold_wall_condensation_warning(sat):
    r = fl.simulate("R410A", 30, sat.p, sat.h_v, 2.5e5, segments(T2=233.15))
    assert any("dew point" in w for w in r.warnings)


def test_solver_hits_target(sat):
    segs = segments()
    value, r, ok = fl.solve_setting("R410A", 10, sat.p, sat.h_v, 2.5e5, segs, 0, 343.15, 273.15, 393.15)
    assert ok
    assert r.outlet.T == pytest.approx(343.15, abs=0.1)


def test_solver_reports_unreachable_target(sat):
    _, r, ok = fl.solve_setting("R410A", 30, sat.p, sat.h_v, 2.5e5, segments(), 0, 423.15, 273.15, 373.15)
    assert not ok and r.outlet.T < 423.15


def test_tank_vapour_withdrawal_cools_and_drops_pressure():
    r = tank.simulate(tank.TankInput(fluid="R410A", withdrawal="vapour", heater="off", duration=6))
    assert r.T[-1] < r.T[0] - 5
    assert r.p[-1] < r.p[0]


def test_tank_liquid_withdrawal_keeps_temperature():
    r = tank.simulate(tank.TankInput(fluid="R410A", withdrawal="liquid", heater="off", duration=6))
    assert r.T[-1] == pytest.approx(r.T[0], abs=1.5)


def test_tank_thermostat_holds_and_matches_steady_power():
    inp = tank.TankInput(fluid="R32", withdrawal="vapour", heater="thermostat", heater_T_set=293.15,
                         heater_power=6000, duration=4)
    r = tank.simulate(inp)
    assert r.T[-1] == pytest.approx(293.15, abs=0.6)
    assert r.q_heater[-1] == pytest.approx(tank.heater_to_hold(inp), rel=0.1)


def test_tank_fractionation_of_zeotropic_blend():
    r = tank.simulate(tank.TankInput(fluid="R407C", withdrawal="vapour", duration=8))
    # vapour leaving is R32-rich; R32 is depleted from the liquid over time
    assert r.feed_composition[0]["R32"] > 0.23
    assert r.liquid_composition[-1]["R32"] < r.liquid_composition[0]["R32"]


def test_tank_liquid_withdrawal_keeps_composition():
    r = tank.simulate(tank.TankInput(fluid="R407C", withdrawal="liquid", duration=8))
    assert r.feed_composition[-1]["R32"] == pytest.approx(0.23, abs=1e-6)
