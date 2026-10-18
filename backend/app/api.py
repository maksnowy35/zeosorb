from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from . import __version__
from .core import materials, pipeline, rosen
from .core.constants import BED_HEIGHT, COLUMN_DIAMETER
from .schemas import BreakthroughRequest, BreakthroughResponse, Curve

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/materials")
def get_materials():
    return {
        "refrigerants": {k: asdict(v) for k, v in materials.refrigerants().items()},
        "zeolites": {k: asdict(v) for k, v in materials.zeolites().items()},
        "adsorption": materials.adsorption(),
    }


def _check_keys(refrigerant: str, zeolite: str) -> None:
    if refrigerant not in materials.refrigerants():
        raise HTTPException(404, f"unknown refrigerant '{refrigerant}'")
    if zeolite not in materials.zeolites():
        raise HTTPException(404, f"unknown zeolite '{zeolite}'")


@router.post("/breakthrough", response_model=BreakthroughResponse)
def breakthrough(req: BreakthroughRequest):
    _check_keys(req.refrigerant, req.zeolite)
    inp = pipeline.BedInput(
        refrigerant=req.refrigerant,
        zeolite=req.zeolite,
        mass_flow=req.mass_flow,
        bed_height=req.bed_height,
        column_diameter=req.column_diameter,
        thresholds=(req.threshold,),
        mode=req.mode,
        tortuosity=req.tortuosity,
    )
    try:
        res = pipeline.run(inp)
    except pipeline.NoAdsorptionData as e:
        raise HTTPException(422, str(e))

    bed = res["bed"]
    t, c = rosen.curve(bed.lam, bed.psi, bed.d_eff, bed.radius, bed.height, bed.w, n=req.curve_points)
    return BreakthroughResponse(
        request=req,
        equilibrium=res["equilibrium"],
        diffusion=res["diffusion"],
        hydraulics=res["hydraulics"],
        film=res["film"],
        rosen=res["rosen"],
        dispersion=res["dispersion"],
        spreading=res["spreading"],
        film_correlation=res["film_correlation"],
        t_stoich=res["t_stoich"],
        t_breakthrough=res["breakthrough"][f"{req.threshold:g}"],
        curve=Curve(t=t.tolist(), c=c.tolist()),
    )


@router.get("/matrix")
def matrix(
    mass_flow: float = Query(30.0, gt=0, le=1000),
    bed_height: float = Query(BED_HEIGHT, gt=0, le=20),
    column_diameter: float = Query(COLUMN_DIAMETER, gt=0, le=5),
    threshold: float = Query(0.05, gt=0, lt=0.5),
    mode: str = Query("corrected", pattern="^(corrected|thesis)$"),
    tortuosity: float = Query(1.0, ge=1.0, le=10.0),
):
    """Breakthrough time for every refrigerant / zeolite pair (None = no isotherm data)."""
    cells = []
    for z in materials.zeolites():
        for r in materials.refrigerants():
            inp = pipeline.BedInput(
                refrigerant=r,
                zeolite=z,
                mass_flow=mass_flow,
                bed_height=bed_height,
                column_diameter=column_diameter,
                thresholds=(threshold,),
                mode=mode,
                tortuosity=tortuosity,
            )
            try:
                res = pipeline.run(inp)
            except pipeline.NoAdsorptionData:
                cells.append({"zeolite": z, "refrigerant": r, "t_breakthrough": None, "Ka": None})
                continue
            cells.append({
                "zeolite": z,
                "refrigerant": r,
                "t_breakthrough": res["breakthrough"][f"{threshold:g}"],
                "Ka": res["equilibrium"]["Ka"],
            })
    return {
        "zeolites": list(materials.zeolites()),
        "refrigerants": list(materials.refrigerants()),
        "cells": cells,
    }
