from typing import Literal

from pydantic import BaseModel, Field

from .core.constants import BED_HEIGHT, COLUMN_DIAMETER

Mode = Literal["corrected", "thesis"]
Model = Literal["rosen", "ldf", "both"]
SweepParameter = Literal["mass_flow", "bed_height", "column_diameter", "tortuosity", "threshold"]


class BedParams(BaseModel):
    mass_flow: float = Field(30.0, gt=0, le=1000, description="kg/h")
    bed_height: float = Field(BED_HEIGHT, gt=0, le=20, description="m")
    column_diameter: float = Field(COLUMN_DIAMETER, gt=0, le=5, description="m")
    threshold: float = Field(0.05, gt=0, lt=0.5, description="breakthrough criterion c/c0")
    mode: Mode = Field("corrected", description="'thesis' reproduces the original thesis tables")
    tortuosity: float = Field(1.0, ge=1.0, le=10.0, description="pore tortuosity factor, D' / tau")


class BreakthroughRequest(BedParams):
    refrigerant: str = Field(examples=["R22"])
    zeolite: str = Field(examples=["4A"])
    model: Model = "both"
    curve_points: int = Field(300, ge=50, le=2000)


class Curve(BaseModel):
    t: list[float]   # s
    c: list[float]   # c/c0


class Profiles(BaseModel):
    zeta: list[float]        # x/H
    t: list[float]           # s
    c: list[list[float]]     # gas phase c/c0, [time][position]
    q: list[list[float]]     # solid loading q/q*(c0)


class SolverInfo(BaseModel):
    n_cells: int
    n_rhs: int
    runtime_ms: float
    stanton: float
    peclet: float
    kappa: float


class Times(BaseModel):
    rosen: float
    ldf: float | None = None


class Curves(BaseModel):
    rosen: Curve | None = None
    ldf: Curve | None = None


class BreakthroughResponse(BaseModel):
    request: BreakthroughRequest
    equilibrium: dict[str, float]
    diffusion: dict[str, float]
    hydraulics: dict[str, float]
    film: dict[str, float]
    film_correlation: str
    rosen: dict[str, float]
    dispersion: dict[str, float]
    spreading: dict[str, float]
    t_stoich: float
    t_breakthrough: Times
    curves: Curves
    profiles: Profiles | None = None
    solver: SolverInfo | None = None


class SeparationRequest(BedParams):
    zeolite: str = Field(examples=["4A"])
    refrigerant_a: str = Field(examples=["R32"])
    refrigerant_b: str = Field(examples=["R125"])
    fraction_a: float = Field(0.5, gt=0, lt=1, description="mass fraction of refrigerant_a in the feed")


class SeparationOption(BaseModel):
    zeolite: str
    weak: str
    strong: str
    alpha: float
    t_weak_full: float
    t_strong_break: float
    window: float


class SeparationResponse(BaseModel):
    request: SeparationRequest
    result: SeparationOption
    curves: dict[str, Curve]
    ranking: list[SeparationOption]


class SweepRequest(BedParams):
    refrigerant: str = Field(examples=["R22"])
    zeolite: str = Field(examples=["4A"])
    parameter: SweepParameter = "mass_flow"
    start: float = Field(gt=0)
    stop: float = Field(gt=0)
    n: int = Field(25, ge=2, le=200)


class SweepResponse(BaseModel):
    parameter: SweepParameter
    x: list[float]
    t_breakthrough: list[float]
    t_stoich: list[float]
    sigma_rel: list[float]
