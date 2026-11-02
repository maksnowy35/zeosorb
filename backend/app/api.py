import time
from dataclasses import asdict

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from . import __version__
from .core import ldf, materials, pipeline, rosen, separation
from .core.constants import BED_HEIGHT, COLUMN_DIAMETER
from .schemas import (
    BedParams, BreakthroughRequest, BreakthroughResponse, Curve, Curves, Profiles,
    SeparationOption, SeparationRequest, SeparationResponse, SolverInfo, SweepRequest,
    SweepResponse, Times,
)

router = APIRouter()


def _check(refrigerants: list[str] = (), zeolite: str | None = None) -> None:
    for r in refrigerants:
        if r not in materials.refrigerants():
            raise HTTPException(404, f"unknown refrigerant '{r}'")
    if zeolite is not None and zeolite not in materials.zeolites():
        raise HTTPException(404, f"unknown zeolite '{zeolite}'")


def _bed_input(p: BedParams, refrigerant: str, zeolite: str, thresholds: tuple[float, ...]) -> pipeline.BedInput:
    return pipeline.BedInput(
        refrigerant=refrigerant,
        zeolite=zeolite,
        mass_flow=p.mass_flow,
        bed_height=p.bed_height,
        column_diameter=p.column_diameter,
        thresholds=thresholds,
        mode=p.mode,
        tortuosity=p.tortuosity,
    )


def _run(inp: pipeline.BedInput) -> dict:
    try:
        return pipeline.run(inp)
    except pipeline.NoAdsorptionData as e:
        raise HTTPException(422, str(e))


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/materials")
def get_materials():
    return {
        "refrigerants": {k: asdict(v) for k, v in materials.refrigerants().items()},
        "zeolites": {k: {**asdict(v), **v.derived()} for k, v in materials.zeolites().items()},
        "adsorption": materials.adsorption(),
        "blends": materials.blends(),
    }


@router.post("/breakthrough", response_model=BreakthroughResponse)
def breakthrough(req: BreakthroughRequest):
    _check([req.refrigerant], req.zeolite)
    res = _run(_bed_input(req, req.refrigerant, req.zeolite, (req.threshold,)))
    bed = res["bed"]
    t_end = 1.6 * res["t_stoich"]

    times = Times(rosen=res["breakthrough"][f"{req.threshold:g}"])
    curves = Curves()
    profiles = solver = None

    if req.model in ("rosen", "both"):
        t, c = rosen.curve(bed.lam, bed.psi, bed.d_eff, bed.radius, bed.height, bed.w,
                           n=req.curve_points, t_max=t_end)
        curves.rosen = Curve(t=t.tolist(), c=c.tolist())

    if req.model in ("ldf", "both"):
        t0 = time.perf_counter()
        sol = ldf.simulate(bed, t_end=t_end, n_out=req.curve_points)
        times.ldf = sol.time_at(req.threshold)
        curves.ldf = Curve(t=sol.t.tolist(), c=sol.c_out.tolist())
        profiles = Profiles(
            zeta=sol.zeta.round(4).tolist(),
            t=sol.t_profiles.tolist(),
            c=sol.c_profiles.round(4).tolist(),
            q=sol.q_profiles.round(4).tolist(),
        )
        solver = SolverInfo(
            n_cells=sol.n_cells, n_rhs=sol.n_rhs, runtime_ms=(time.perf_counter() - t0) * 1000,
            stanton=sol.stanton, peclet=sol.peclet, kappa=sol.kappa,
        )

    return BreakthroughResponse(
        request=req,
        equilibrium=res["equilibrium"],
        diffusion=res["diffusion"],
        hydraulics=res["hydraulics"],
        film=res["film"],
        film_correlation=res["film_correlation"],
        rosen=res["rosen"],
        dispersion=res["dispersion"],
        spreading=res["spreading"],
        t_stoich=res["t_stoich"],
        t_breakthrough=times,
        curves=curves,
        profiles=profiles,
        solver=solver,
    )


@router.get("/matrix")
def matrix(
    mass_flow: float = Query(30.0, gt=0, le=1000),
    bed_height: float = Query(BED_HEIGHT, gt=0, le=20),
    column_diameter: float = Query(COLUMN_DIAMETER, gt=0, le=5),
    threshold: float = Query(0.05, gt=0, lt=0.5),
    mode: str = Query("corrected", pattern="^(corrected|thesis)$"),
    tortuosity: float | None = Query(None, ge=1.0, le=10.0),
):
    """Breakthrough time (Rosen) and key parameters for every pair. None = no isotherm data."""
    p = BedParams(mass_flow=mass_flow, bed_height=bed_height, column_diameter=column_diameter,
                  threshold=threshold, mode=mode, tortuosity=tortuosity)
    cells = []
    for z in materials.zeolites():
        for r in materials.refrigerants():
            cell = {"zeolite": z, "refrigerant": r}
            try:
                res = pipeline.run(_bed_input(p, r, z, (threshold,)))
            except pipeline.NoAdsorptionData:
                cells.append({**cell, "t_breakthrough": None, "t_stoich": None, "Ka": None,
                              "lambda": None, "sigma_rel": None})
                continue
            cells.append({
                **cell,
                "t_breakthrough": res["breakthrough"][f"{threshold:g}"],
                "t_stoich": res["t_stoich"],
                "Ka": res["equilibrium"]["Ka"],
                "lambda": res["rosen"]["lambda"],
                "sigma_rel": res["spreading"]["sigma_rel"],
            })
    return {
        "zeolites": list(materials.zeolites()),
        "refrigerants": list(materials.refrigerants()),
        "cells": cells,
    }


def _option(r: separation.PairResult) -> SeparationOption:
    return SeparationOption(zeolite=r.zeolite, weak=r.weak, strong=r.strong, alpha=r.alpha,
                            t_weak_full=r.t_weak_full, t_strong_break=r.t_strong_break, window=r.window)


@router.post("/separation", response_model=SeparationResponse)
def separate(req: SeparationRequest):
    a, b = req.refrigerant_a, req.refrigerant_b
    _check([a, b], req.zeolite)
    if a == b:
        raise HTTPException(422, "pick two different refrigerants")

    def evaluate(zeolite: str) -> separation.PairResult:
        return separation.evaluate(a, b, _bed_input(req, a, zeolite, ()), req.threshold, req.fraction_a)

    try:
        main = evaluate(req.zeolite)
    except pipeline.NoAdsorptionData as e:
        raise HTTPException(422, str(e))

    ranking = []
    for z in materials.zeolites():
        try:
            ranking.append(_option(main if z == req.zeolite else evaluate(z)))
        except pipeline.NoAdsorptionData:
            continue
    ranking.sort(key=lambda o: o.window, reverse=True)

    t_max = 1.4 * max(r["t_stoich"] for r in main.results.values())
    curves = {}
    for ref, res in main.results.items():
        t, c = separation.curve_for(res, t_max=t_max)
        curves[ref] = Curve(t=t.tolist(), c=c.tolist())

    return SeparationResponse(request=req, result=_option(main), curves=curves, ranking=ranking)


@router.post("/sweep", response_model=SweepResponse)
def sweep(req: SweepRequest):
    _check([req.refrigerant], req.zeolite)
    if req.parameter == "threshold" and not (0 < req.start < 0.5 and 0 < req.stop < 0.5):
        raise HTTPException(422, "threshold sweep must stay within (0, 0.5)")
    if req.parameter == "tortuosity" and min(req.start, req.stop) < 1:
        raise HTTPException(422, "tortuosity must be >= 1")

    xs = np.linspace(req.start, req.stop, req.n)
    out = {"t_breakthrough": [], "t_stoich": [], "sigma_rel": []}
    for x in xs:
        p = req.model_copy(update={req.parameter: float(x)})
        res = _run(_bed_input(p, req.refrigerant, req.zeolite, (p.threshold,)))
        out["t_breakthrough"].append(res["breakthrough"][f"{p.threshold:g}"])
        out["t_stoich"].append(res["t_stoich"])
        out["sigma_rel"].append(res["spreading"]["sigma_rel"])
    return SweepResponse(parameter=req.parameter, x=xs.tolist(), **out)
