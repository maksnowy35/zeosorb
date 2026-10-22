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
    """
    One adsorbent. The first block is what the thesis uses directly; grain_volume,
    grain_mass and pore_volume are the raw numbers from thesis ch. 4 and everything
    about the bed structure is derived from them below.

    Pellet (binder macropore) properties are not in the thesis - they are typical
    values for commercial beads, see pellet_source.
    """
    key: str
    name: str
    grain_radius: float        # m
    pore_diameter: float       # Angstrom, zeolite window
    bed_porosity: float        # -, as computed in the thesis: (rho_p - rho_n) / rho_p
    bulk_density: float        # kg/m3, rho_n
    channel_diameter: float    # m (equivalent channel diameter dz)
    grain_volume: float        # m3, V_k of one grain
    grain_mass: float          # kg, m_k of one grain
    pore_volume: float         # m3/kg, zeolite micropore volume v_p as used in the thesis
    micropore_volume: float    # cm3/g, typical value for commercial pellets (binder included), Langmuir q_m
    macroporosity: float       # -, binder macropores in the grain, eps_M
    macropore_diameter: float  # m
    tortuosity: float          # -, macropore tortuosity factor
    source: str
    pellet_source: str

    @property
    def envelope_density(self) -> float:
        """Grain mass over the whole grain volume, m_k / V_k [kg/m3]."""
        return self.grain_mass / self.grain_volume

    @property
    def thesis_particle_density(self) -> float:
        """rho_p from the thesis: m_k / (V_k - V_por), the pores taken out of the grain volume."""
        return self.grain_mass / (self.grain_volume - self.pore_volume * self.grain_mass)

    @property
    def interparticle_voidage(self) -> float:
        """Space between the grains only, 1 - rho_n / (m_k / V_k)."""
        return 1.0 - self.bulk_density / self.envelope_density

    @property
    def micropore_fraction(self) -> float:
        """Zeolite micropore volume per grain volume, v_p m_k / V_k."""
        return self.pore_volume * self.envelope_density

    def derived(self) -> dict[str, float]:
        return {
            "envelope_density": self.envelope_density,
            "thesis_particle_density": self.thesis_particle_density,
            "interparticle_voidage": self.interparticle_voidage,
            "micropore_fraction": self.micropore_fraction,
        }


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
