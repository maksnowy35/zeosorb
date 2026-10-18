from pydantic import BaseModel, Field

from .core.constants import BED_HEIGHT, COLUMN_DIAMETER


class BreakthroughRequest(BaseModel):
    refrigerant: str = Field(examples=["R22"])
    zeolite: str = Field(examples=["4A"])
    mass_flow: float = Field(30.0, gt=0, le=1000, description="kg/h")
    bed_height: float = Field(BED_HEIGHT, gt=0, le=20, description="m")
    column_diameter: float = Field(COLUMN_DIAMETER, gt=0, le=5, description="m")
    threshold: float = Field(0.05, gt=0, lt=0.5, description="breakthrough criterion c/c0")
    curve_points: int = Field(300, ge=50, le=2000)


class Curve(BaseModel):
    t: list[float]
    c: list[float]


class BreakthroughResponse(BaseModel):
    request: BreakthroughRequest
    equilibrium: dict[str, float]
    diffusion: dict[str, float]
    hydraulics: dict[str, float]
    film: dict[str, float]
    rosen: dict[str, float]
    t_stoich: float
    t_breakthrough: float
    curve: Curve
