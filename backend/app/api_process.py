"""Process endpoints: feed line from the storage tank and the two-bed cycle."""
import numpy as np
from fastapi import APIRouter, HTTPException

from .core import cycle, feed, feedline, fluids, materials, tank
from .schemas_process import CycleRequest, FeedRequest, FeedSolveRequest

router = APIRouter()
C0 = 273.15


# ---- feed ------------------------------------------------------------------------------------

def _setup(req: FeedRequest) -> feed.FeedSetup:
    if req.fluid not in fluids.FLUIDS:
        raise HTTPException(404, f"unknown fluid '{req.fluid}'")
    if req.zeolite not in materials.zeolites():
        raise HTTPException(404, f"unknown zeolite '{req.zeolite}'")
    t_amb = req.tank.T_amb_C + C0
    segments = [
        feedline.Segment(
            name=s.name, D=s.D_mm / 1000.0, L=s.L_m,
            heating=feedline.Heating(
                kind=s.heating.kind, T_medium=s.heating.T_medium_C + C0, h_medium=s.heating.h_medium,
                q_trace=s.heating.q_trace_W_m, insulation=s.heating.insulation_mm / 1000.0, T_amb=t_amb,
            ),
        )
        for s in req.segments
    ]
    tk = tank.TankInput(
        fluid=req.fluid, volume=req.tank.volume_L / 1000.0, fill_mass=req.tank.fill_kg,
        T0=req.tank.T0_C + C0, T_amb=t_amb, withdrawal=req.tank.withdrawal, heater=req.tank.heater,
        heater_T_set=req.tank.heater_T_C + C0, heater_power=req.tank.heater_kW * 1000.0,
        mass_flow=req.mass_flow, duration=req.campaign_h,
    )
    return feed.FeedSetup(fluid=req.fluid, mass_flow=req.mass_flow, reducer=req.reducer_bar * 1e5, tank=tk,
                          segments=segments, target=req.target_C + C0, superheat_min=req.superheat_min_K,
                          zeolite=req.zeolite)


def _analyse(setup: feed.FeedSetup) -> dict:
    try:
        return feed.analyse(setup)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/process/defaults")
def defaults():
    return {
        "feed": FeedRequest().model_dump(),
        "cycle": {"bed": CycleRequest.model_fields["bed"].default.model_dump(),
                  "plant": CycleRequest.model_fields["plant"].default.model_dump()},
        "presets": cycle.presets(),
        "bed_presets": {
            "pilot": {"label": "Pilot column, D 0.2 m x 1.0 m", "diameter_m": 0.2, "height_m": 1.0},
            "lab": {"label": "Lab column, D 0.07 m x 0.25 m", "diameter_m": 0.07, "height_m": 0.25},
            "thesis": {"label": "Thesis column, D 0.5 m x 2.89 m", "diameter_m": 0.5, "height_m": 2.89},
        },
        "fluids": list(fluids.FLUIDS),
    }


@router.post("/feed")
def feed_line(req: FeedRequest):
    return _analyse(_setup(req))


@router.post("/feed/solve")
def feed_solve(req: FeedSolveRequest):
    if req.segment >= len(req.segments):
        raise HTTPException(422, "no such segment")
    setup = _setup(req)
    seg = setup.segments[req.segment]
    if seg.heating.kind not in ("medium", "trace"):
        raise HTTPException(422, "only a jacket (medium) or a trace can be adjusted")
    if seg.heating.kind == "medium":
        lo = (req.lo if req.lo is not None else -40.0) + C0
        hi = (req.hi if req.hi is not None else 200.0) + C0
    else:
        lo = req.lo if req.lo is not None else 0.0
        hi = req.hi if req.hi is not None else 2000.0
    p_in, h_in = feed.tank_outlet(setup, setup.tank.T0)
    value, _, reached = feedline.solve_setting(setup.fluid, setup.mass_flow, p_in, h_in, setup.reducer,
                                               setup.segments, req.segment, setup.target, lo, hi)
    res = _analyse(setup)    # segments now carry the solved value
    res["solved"] = {
        "segment": req.segment, "kind": seg.heating.kind, "reached": reached,
        "value": value - C0 if seg.heating.kind == "medium" else value,
        "unit": "°C" if seg.heating.kind == "medium" else "W/m",
        "bound_hit": abs(value - lo) < 1e-6 or abs(value - hi) < 1e-6,
    }
    return res


# ---- cycle -----------------------------------------------------------------------------------

def _cycle_inputs(req: CycleRequest):
    p = req.plant
    if p.feed_composition:
        comp = {k: v for k, v in p.feed_composition.items() if v > 0}
    else:
        comp = fluids.components(p.feed)
    for n in comp:
        if n not in materials.refrigerants():
            raise HTTPException(404, f"unknown refrigerant '{n}'")
    total = sum(comp.values())
    comp = {k: v / total for k, v in comp.items()}
    if req.bed.zeolite not in materials.zeolites():
        raise HTTPException(404, f"unknown zeolite '{req.bed.zeolite}'")
    missing = [n for n in comp if materials.adsorbed_amount(req.bed.zeolite, n) is None]
    if missing:
        raise HTTPException(422, f"no isotherm data for {', '.join(missing)} on {req.bed.zeolite}")

    spec = cycle.BedSpec(zeolite=req.bed.zeolite, diameter=req.bed.diameter_m, height=req.bed.height_m,
                         wall=req.bed.wall_mm / 1000.0, h_wall=req.bed.h_wall, k_bed=req.bed.k_bed,
                         tortuosity=req.bed.tortuosity, cells=req.bed.cells)
    purge = {p.purge_gas: 1.0} if p.purge_gas else None
    if purge and p.purge_gas not in comp:
        raise HTTPException(422, f"the purge gas {p.purge_gas} is not part of the feed")
    plant = cycle.Plant(
        feed=comp, feed_T=p.feed_T_C + C0, feed_pressure=cycle.from_barg(p.feed_barg), feed_flow=p.feed_flow,
        product_pressure=cycle.from_barg(p.product_barg), product_flow=p.product_flow,
        vacuum_speed=p.vacuum_speed, vacuum_ultimate=max(cycle.from_barg(p.vacuum_barg), 200.0),
        vacuum_max_flow=p.vacuum_max_flow, purge_gas=purge, purge_flow=max(p.purge_flow, 1e-6),
        purge_T=p.purge_T_C + C0, purge_pressure=cycle.from_barg(p.purge_barg),
        jacket={k: (None if v is None else v + C0) for k, v in p.jacket_C.items()},
        T_amb=p.T_amb_C + C0,
    )
    steps = cycle.steps_from_table([s.model_dump() for s in req.steps])
    return spec, plant, steps


def _round(obj):
    if isinstance(obj, float):
        return float(f"{obj:.5g}") if np.isfinite(obj) else None
    if isinstance(obj, (np.floating,)):
        return _round(float(obj))
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


@router.post("/cycle")
def run_cycle(req: CycleRequest):
    spec, plant, steps = _cycle_inputs(req)
    try:
        res = cycle.run(spec, plant, steps, semantics=req.semantics, max_cycles=req.max_cycles)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, f"the cycle could not be simulated: {e}")

    # display units: bar g, °C, kg/h
    s = res["series"]
    for b in ("A", "B"):
        s[b]["P"] = [cycle.barg(v) for v in s[b]["P"]]
        for k in ("T_top", "T_mid", "T_bottom", "T_mean"):
            s[b][k] = [v - C0 for v in s[b][k]]
    for st in res["steps"]:
        for info in st["beds"].values():
            for k in ("P_start", "P_end", "P_min", "P_max"):
                info[k] = cycle.barg(info[k])
            for k in ("T_start", "T_end"):
                info[k] -= C0
            if info["jacket_T"] is not None:
                info["jacket_T"] -= C0
    th = res["thermal"]
    for k in ("T_mean_min", "T_mean_max", "T_max"):
        th[k] -= C0
    res["profiles"] = [{"q": p["q"], "T": [v - C0 for v in p["T"]]} for p in res["profiles"]]
    return _round(res)
