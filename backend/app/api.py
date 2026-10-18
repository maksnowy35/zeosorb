from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from . import __version__
from .core import materials, pipeline, rosen
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
    )
    try:
        res = pipeline.run(inp)
    except pipeline.NoAdsorptionData as e:
        raise HTTPException(422, str(e))

    t, c = rosen.curve(*res["_curve_args"], n=req.curve_points)
    return BreakthroughResponse(
        request=req,
        equilibrium=res["equilibrium"],
        diffusion=res["diffusion"],
        hydraulics=res["hydraulics"],
        film=res["film"],
        rosen=res["rosen"],
        t_stoich=res["t_stoich"],
        t_breakthrough=res["breakthrough"][f"{req.threshold:g}"],
        curve=Curve(t=t.tolist(), c=c.tolist()),
    )
