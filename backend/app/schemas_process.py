"""Request models for the process endpoints (feed line, cycle). Units are the ones an operator uses:
°C, bar (absolute for the reducer, gauge for the cycle steps), mm, kg/h."""
from typing import Literal

from pydantic import BaseModel, Field

HeatingKind = Literal["medium", "trace", "insulated", "bare"]
CycleMode = Literal["fill", "adsorb", "blowdown", "evacuate", "purge", "idle"]


class HeatingIn(BaseModel):
    kind: HeatingKind = "medium"
    T_medium_C: float = Field(90.0, ge=-60, le=300, description="jacket fluid temperature")
    h_medium: float = Field(1000.0, gt=0, le=20000, description="jacket side coefficient, W/m2K")
    q_trace_W_m: float = Field(0.0, ge=0, le=5000, description="electric trace power per metre")
    insulation_mm: float = Field(30.0, ge=0, le=300)


class SegmentIn(BaseModel):
    name: str = "Segment"
    D_mm: float = Field(gt=2, le=500, description="inner diameter")
    L_m: float = Field(gt=0, le=200)
    heating: HeatingIn = HeatingIn()


class TankIn(BaseModel):
    volume_L: float = Field(1000.0, gt=1, le=50000)
    fill_kg: float = Field(800.0, gt=0, le=60000)
    T0_C: float = Field(20.0, ge=-40, le=60)
    T_amb_C: float = Field(20.0, ge=-30, le=50)
    withdrawal: Literal["vapour", "liquid"] = "vapour"
    heater: Literal["off", "thermostat", "power"] = "off"
    heater_T_C: float = Field(20.0, ge=-30, le=55)
    heater_kW: float = Field(3.0, ge=0, le=100)


def _default_segments() -> list[SegmentIn]:
    return [
        SegmentIn(name="Segment 1", D_mm=40, L_m=3.0, heating=HeatingIn(kind="medium", T_medium_C=90)),
        SegmentIn(name="Segment 2", D_mm=90, L_m=2.0, heating=HeatingIn(kind="medium", T_medium_C=100)),
    ]


class FeedRequest(BaseModel):
    fluid: str = Field("R410A", examples=["R410A"])
    mass_flow: float = Field(30.0, gt=0, le=2000, description="kg/h")
    reducer_bar: float = Field(2.5, gt=0.05, le=40, description="reducer outlet, bar abs")
    tank: TankIn = TankIn()
    segments: list[SegmentIn] = Field(default_factory=_default_segments, min_length=1, max_length=5)
    target_C: float = Field(100.0, ge=-40, le=300, description="wanted gas temperature at the adsorber")
    superheat_min_K: float = Field(10.0, ge=0, le=100)
    campaign_h: float = Field(8.0, gt=0, le=72)
    zeolite: str = Field("13X", description="bed used for the capacity-vs-temperature curve")


class FeedSolveRequest(FeedRequest):
    segment: int = Field(0, ge=0, le=4, description="which segment's jacket temperature / trace power to adjust")
    lo: float | None = Field(None, description="lower bound, °C for a jacket, W/m for a trace")
    hi: float | None = Field(None, description="upper bound, °C for a jacket, W/m for a trace")


class CycleBedIn(BaseModel):
    zeolite: str = "13X"
    diameter_m: float = Field(0.2, gt=0.01, le=3)
    height_m: float = Field(1.0, gt=0.05, le=10)
    wall_mm: float = Field(5.0, gt=0, le=50)
    h_wall: float = Field(50.0, gt=1, le=1000, description="bed-to-wall coefficient, W/m2K")
    k_bed: float = Field(0.2, gt=0.01, le=10, description="effective radial conductivity of the packing, W/mK")
    tortuosity: float = Field(1.0, ge=1, le=10)
    cells: int = Field(16, ge=6, le=40)


class CyclePlantIn(BaseModel):
    feed: str = Field("R410A", description="refrigerant or blend")
    feed_composition: dict[str, float] | None = Field(None, description="mass fractions, overrides the blend's nominal one")
    feed_T_C: float = Field(100.0, ge=-40, le=300)
    feed_barg: float = Field(1.5, ge=-0.95, le=20)
    feed_flow: float = Field(10.0, gt=0, le=2000, description="kg/h")
    product_barg: float = Field(1.0, ge=-0.95, le=20, description="back-pressure on the product line")
    product_flow: float = Field(2.5, gt=0, le=2000, description="kg/h with the product valve fully open")
    vacuum_speed: float = Field(15.0, gt=0, le=5000, description="m3/h at suction")
    vacuum_barg: float = Field(-0.9, ge=-1.0, le=0.0, description="lowest pressure of the vacuum source")
    vacuum_max_flow: float = Field(20.0, gt=0, le=5000, description="kg/h")
    purge_gas: str | None = Field(None, description="component used for purging, default: the weakest-held one")
    purge_flow: float = Field(0.3, ge=0, le=2000, description="kg/h")
    purge_T_C: float = Field(150.0, ge=-40, le=400)
    purge_barg: float = Field(5.0, ge=-0.95, le=40)
    jacket_C: dict[CycleMode, float | None] = Field(default_factory=lambda: {
        "fill": 100.0, "adsorb": 100.0, "blowdown": 200.0, "evacuate": 200.0, "purge": 200.0, "idle": None,
    })
    T_amb_C: float = Field(20.0, ge=-30, le=50)


class StepIn(BaseModel):
    name: str
    label: str = ""
    duration: float = Field(gt=0, le=86400, description="s")
    bed_a: CycleMode
    bed_b: CycleMode
    control: Literal["A", "B"] | None = None
    direction: Literal[">", "<"] = ">"
    setpoint: float | None = Field(None, ge=-1.0, le=40, description="bar g")
    purge_pressure: float | None = Field(None, ge=-1.0, le=40, description="bar g")


class CycleRequest(BaseModel):
    bed: CycleBedIn = CycleBedIn()
    plant: CyclePlantIn = CyclePlantIn()
    steps: list[StepIn] = Field(min_length=1, max_length=24)
    semantics: Literal["controller", "transition"] = "controller"
    max_cycles: int = Field(14, ge=1, le=40)
