"""Material data (refrigerants, zeolites, adsorption points) loaded from app/data/*.json."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Refrigerant:
    key: str
    name: str
    formula: str
    molar_mass: float      # kg/kmol
    molecule_size: float   # Angstrom
    viscosity: float       # Pa*s at 100 C, 0.8 bar
    gwp_ar4: float


@dataclass(frozen=True)
class Zeolite:
    key: str
    name: str
    grain_radius: float      # m
    pore_diameter: float     # Angstrom
    bed_porosity: float      # -
    bulk_density: float      # kg/m3
    channel_diameter: float  # m (equivalent channel diameter dz)
    source: str


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def refrigerants() -> dict[str, Refrigerant]:
    return {k: Refrigerant(key=k, **v) for k, v in _load("refrigerants.json").items()}


@lru_cache
def zeolites() -> dict[str, Zeolite]:
    return {k: Zeolite(key=k, **v) for k, v in _load("zeolites.json").items()}


@lru_cache
def adsorption() -> dict[str, dict[str, float]]:
    return _load("adsorption.json")["data"]


def adsorbed_amount(zeolite: str, refrigerant: str) -> float | None:
    """q [mol/kg] at 0.8 bar or None if there is no data for the pair."""
    return adsorption().get(zeolite, {}).get(refrigerant)


@lru_cache
def blends() -> dict[str, dict[str, float]]:
    return _load("blends.json")["data"]
