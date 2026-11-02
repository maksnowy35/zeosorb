import numpy as np
import pytest

from app.core import cycle

FAST = cycle.BedSpec(cells=8)


def ten_steps():
    return cycle.steps_from_table(cycle.presets()["two_bed_10_step"]["steps"])


@pytest.fixture(scope="module")
def ten_result():
    return cycle.run(FAST, cycle.Plant(), ten_steps(), max_cycles=14)


def test_presets_load():
    p = cycle.presets()
    assert len(p["two_bed_10_step"]["steps"]) == 10
    s = ten_steps()
    assert s[0].setpoint == pytest.approx(cycle.from_barg(1.0))
    assert s[4].setpoint is None and s[4].purge_pressure == pytest.approx(cycle.from_barg(4.0))


def test_reaches_cyclic_steady_state(ten_result):
    assert ten_result["css"]
    assert ten_result["convergence"][-1] < 2e-3


def test_mass_balance_closes(ten_result):
    assert ten_result["kpi"]["mass_balance_error"] < 2e-3


def test_cycle_time_is_sum_of_steps(ten_result):
    assert ten_result["kpi"]["cycle_time_h"] * 3600 == pytest.approx(sum(s.duration for s in ten_steps()))


def test_product_is_enriched_in_weak_component(ten_result):
    k = ten_result["kpi"]
    assert k["weak"] == "R125" and k["strong"] == "R32"
    assert k["product_purity"] > 0.5          # feed is 50 %
    assert k["extract_purity"] > 0.5


def test_unreachable_vacuum_setpoint_is_reported(ten_result):
    text = " ".join(f["text"] for f in ten_result["findings"])
    assert "-0.95" in text and "vacuum source" in text


def test_evacuation_stops_at_vacuum_floor():
    plant = cycle.Plant(vacuum_ultimate=0.3e5)
    res = cycle.run(FAST, plant, ten_steps(), max_cycles=2)
    p_min = min(min(res["series"][b]["P"]) for b in ("A", "B"))
    assert p_min > 0.3e5 - 500


def test_controller_holds_fill_at_setpoint():
    steps = [cycle.Step("fill", 7200, "fill", "idle", "A", ">", cycle.from_barg(0.5))]
    res = cycle.run(FAST, cycle.Plant(feed_flow=20), steps, max_cycles=1)
    p_end = res["steps"][0]["beds"]["A"]["P_end"]
    assert cycle.barg(p_end) == pytest.approx(0.5, abs=0.03)


def test_transition_semantics_ends_step_at_setpoint():
    steps = [cycle.Step("fill", 7200, "fill", "idle", "A", ">", cycle.from_barg(0.5)),
             cycle.Step("hold", 100, "idle", "idle")]
    res = cycle.run(FAST, cycle.Plant(feed_flow=20), steps, semantics="transition", max_cycles=1)
    s = res["steps"][0]
    assert s["ended_by"] == "setpoint"
    assert s["duration"] < 7200
    assert cycle.barg(s["beds"]["A"]["P_end"]) == pytest.approx(0.5, abs=0.01)


def test_immediate_end_is_detected():
    steps = [cycle.Step("evacuate", 3000, "evacuate", "idle", "A", "<", cycle.from_barg(-0.88)),
             cycle.Step("again", 3000, "evacuate", "idle", "A", "<", cycle.from_barg(-0.85))]
    res = cycle.run(FAST, cycle.Plant(), steps, semantics="transition", max_cycles=1)
    assert res["steps"][0]["ended_by"] == "setpoint"
    assert res["steps"][1]["ended_by"] == "immediate"
    assert any("ends the moment it starts" in f["text"] for f in res["findings"])


def test_shared_feed_goes_to_the_bed_at_lower_pressure():
    steps = [cycle.Step("both", 600, "fill", "adsorb")]
    plant = cycle.Plant()
    bed = cycle.Bed(FAST, plant)
    fa, fb = bed.feed_header([np.array([0.3e5]), np.array([2.4e5])], [None, None])
    assert fa[0] > 5 * fb[0]
    assert fa[0] + fb[0] <= bed.n_feed * 1.0001
    res = cycle.run(FAST, plant, steps, max_cycles=1)
    assert res["kpi"]["mass_balance_error"] < 2e-3


def test_hotter_jacket_desorbs_more():
    small = dict(feed_flow=1.0, product_flow=0.25, vacuum_speed=2.0, purge_flow=0.03)
    cold = cycle.Plant(**small, jacket={"fill": 373.15, "adsorb": 373.15, "blowdown": 373.15, "evacuate": 373.15,
                                        "purge": 373.15, "idle": None})
    hot = cycle.Plant(**small)
    thin = cycle.BedSpec(cells=8, diameter=0.07, height=0.5)
    r_cold = cycle.run(thin, cold, ten_steps(), max_cycles=3)
    r_hot = cycle.run(thin, hot, ten_steps(), max_cycles=3)
    q_cold = r_cold["steps"][-1]["beds"]["A"]["q_end"]
    q_hot = r_hot["steps"][-1]["beds"]["A"]["q_end"]
    assert sum(q_hot) < sum(q_cold)


def test_thermal_time_constant_scales_with_diameter():
    small = cycle.Bed(cycle.BedSpec(diameter=0.07), cycle.Plant())
    big = cycle.Bed(cycle.BedSpec(diameter=0.5), cycle.Plant())
    assert big.thermal_time_constant > 10 * small.thermal_time_constant


def test_bed_uses_corrected_structure_and_grain_kinetics():
    from app.core import materials

    bed = cycle.Bed(FAST, cycle.Plant())
    zeo = materials.zeolites()[FAST.zeolite]
    # gas between the grains + in their macropores, not the thesis total voidage
    assert bed.eps == pytest.approx(zeo.interparticle_voidage + (1 - zeo.interparticle_voidage) * zeo.macroporosity)
    assert bed.tau == zeo.tortuosity
    # LDF time constant of the grains at the thesis point: minutes, not seconds
    y = bed.initial(373.15, 0.8e5 + 1e5)
    k = bed.ldf_coefficients(y)
    assert 30 < 1 / k.max() < 3000
