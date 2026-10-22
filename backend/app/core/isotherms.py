"""
Temperature- and pressure-dependent isotherms for the cycle model.

Extended Langmuir, with b following van 't Hoff:

    q_i = q_m,i b_i p_i / (1 + sum_j b_j p_j),     b_i(T) = b_ref,i exp[dH_i / R (1/T - 1/T_ref)]

Each pair is anchored to the thesis point (q at 0.8 bar and 100 C), so at the thesis conditions the
cycle model and the Rosen pipeline see the same equilibrium. The saturation capacity and the heat of
adsorption are estimates (see app/data/isotherms.json) - good enough to see trends and compare cycle
settings, not to size a plant.
"""
import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import fluids, materials

R = fluids.R_GAS


@dataclass(frozen=True)
class Langmuir:
    zeolite: str
    refrigerant: str
    q_m: float        # mol/kg
    b_ref: float      # 1/bar at T_ref
    dH: float         # J/mol, positive = exothermic
    T_ref: float      # K
    estimated: bool

    def b(self, T):
        return self.b_ref * np.exp(self.dH / R * (1.0 / np.asarray(T) - 1.0 / self.T_ref))

    def q(self, p_bar, T):
        bp = self.b(T) * np.asarray(p_bar)
        return self.q_m * bp / (1.0 + bp)


@lru_cache
def _config() -> dict:
    with open(materials.DATA_DIR / "isotherms.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def langmuir(zeolite: str, refrigerant: str) -> Langmuir:
    cfg = _config()
    q_ref = materials.adsorbed_amount(zeolite, refrigerant)
    if q_ref is None:
        raise ValueError(f"no adsorption data for {refrigerant} on {zeolite}")
    over = cfg["overrides"].get(zeolite, {}).get(refrigerant, {})

    fl = fluids.fluid(refrigerant)
    T_nb = fl.T_normal_boiling()
    s = fl.sat_T(T_nb)
    v_molar = fl.M / s.rho_l * 1e6                      # cm3/mol
    q_m = materials.zeolites()[zeolite].micropore_volume * 1000.0 / v_molar   # mol/kg
    q_m = max(q_m, cfg["min_capacity_ratio"] * q_ref)
    dH = cfg["isosteric_factor"] * s.h_fg * fl.M        # J/mol

    q_m = over.get("q_m", q_m)
    dH = over.get("dH", dH)
    b_ref = q_ref / (cfg["p_ref_bar"] * (q_m - q_ref))
    return Langmuir(zeolite, refrigerant, q_m, b_ref, dH, cfg["T_ref"], estimated=not over)


class Mixture:
    """Extended Langmuir for the components fed together, vectorised over cells."""

    def __init__(self, zeolite: str, names: list[str]):
        self.items = [langmuir(zeolite, n) for n in names]
        self.q_m = np.array([i.q_m for i in self.items])
        self.b_ref = np.array([i.b_ref for i in self.items])
        self.dH = np.array([i.dH for i in self.items])
        self.T_ref = self.items[0].T_ref

    def q_star(self, p_bar: np.ndarray, T: np.ndarray) -> np.ndarray:
        """p_bar: partial pressures (..., nc), T broadcastable to (...,). Returns (..., nc)."""
        b = self.b_ref * np.exp(self.dH / R * (1.0 / T[..., None] - 1.0 / self.T_ref))
        bp = b * p_bar
        return self.q_m * bp / (1.0 + bp.sum(axis=-1, keepdims=True))


def capacity_curve(zeolite: str, composition_mass: dict[str, float], p: float, temperatures) -> dict:
    """Equilibrium loading of each component of a feed at total pressure p [Pa] over temperatures [K]."""
    names = list(composition_mass)
    y = fluids.mass_to_mole(composition_mass)
    mix = Mixture(zeolite, names)
    T = np.asarray(temperatures, dtype=float)
    p_bar = np.array([y[n] * p / 1e5 for n in names])
    q = mix.q_star(np.broadcast_to(p_bar, (len(T), len(names))), T)
    refs = materials.refrigerants()
    kg = q * np.array([refs[n].molar_mass / 1000.0 for n in names])   # kg/kg zeolite
    return {"names": names, "q_mol": q, "q_kg": kg}
