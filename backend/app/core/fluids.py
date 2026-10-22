"""
Thermophysical properties of the refrigerants (CoolProp, HEOS backend).

Single refrigerants are real pure fluids. Blends (R410A, R407C, R404A, R507A) are used in two ways:
- as CoolProp pseudo-pure fluids for the pipe flow (fast and robust, no temperature glide),
- as true mixtures of their components (Blend) where the composition matters: the bubble point
  in a storage tank, the composition of the vapour drawn off it and the dew point in the line.
"""
from dataclasses import dataclass
from functools import lru_cache

import CoolProp
from CoolProp.CoolProp import AbstractState

from . import materials

P_ATM = 101325.0
R_GAS = 8.314462618  # J/(mol K)

FLUIDS = ("R32", "R22", "R134a", "R143a", "R125", "R152a", "R410A", "R407C", "R404A", "R507A")


@dataclass(frozen=True)
class Saturation:
    """Saturated liquid and vapour at one temperature / pressure."""
    T: float        # K (dew temperature for pseudo-pure blends)
    p: float        # Pa
    h_l: float      # J/kg
    h_v: float
    rho_l: float    # kg/m3
    rho_v: float
    mu_l: float     # Pa s
    mu_v: float
    k_l: float      # W/(m K)
    k_v: float
    cp_l: float     # J/(kg K)
    cp_v: float
    T_l: float = 0.0   # K, bubble temperature at p (differs from T only for blends with a glide)

    @property
    def h_fg(self) -> float:
        return self.h_v - self.h_l


@dataclass(frozen=True)
class State:
    p: float              # Pa
    T: float              # K
    h: float              # J/kg
    rho: float            # kg/m3 (homogeneous in the two-phase region)
    mu: float             # Pa s (McAdams in the two-phase region)
    k: float              # W/(m K)
    cp: float             # J/(kg K)
    x: float | None       # vapour quality, None outside the two-phase region
    T_dew: float          # K, saturated vapour temperature at p
    phase: str            # "liquid" | "two-phase" | "vapour"

    @property
    def superheat(self) -> float:
        """T - T_dew. Negative for liquid, zero for a two-phase mixture."""
        return self.T - self.T_dew if self.phase != "two-phase" else 0.0


class Fluid:
    """One refrigerant or a pseudo-pure blend."""

    def __init__(self, key: str):
        if key not in FLUIDS:
            raise ValueError(f"unknown fluid '{key}'")
        self.key = key
        self._as = AbstractState("HEOS", key)
        self._sat_as = AbstractState("HEOS", key)   # separate object: saturation lookups must not
                                                     # overwrite the state being evaluated
        self.M = self._as.molar_mass()          # kg/mol
        self.T_crit = self._as.T_critical()
        self.p_crit = self._as.p_critical()

    # ---- saturation ---------------------------------------------------------------

    def _phase_props(self, inputs: int, value: float, q: float) -> tuple:
        a = self._sat_as
        if inputs == CoolProp.PQ_INPUTS:
            a.update(inputs, value, q)
        else:
            a.update(inputs, q, value)
        T, p, h, rho, cp = a.T(), a.p(), a.hmass(), a.rhomass(), a.cpmass()
        mu, k = self._transport(a, p, T, side=1.0 if q > 0.5 else -1.0)
        return T, p, h, rho, mu, k, cp

    def _transport(self, a: AbstractState, p: float, T: float, side: float = 1.0) -> tuple[float, float]:
        """Viscosity and conductivity at the current state of a. Some transport models (ECS, R32 vapour
        at low pressure) fail on or near the saturation line; then take them a little further into
        the single-phase region."""
        try:
            return a.viscosity(), a.conductivity()
        except ValueError:
            pass
        for dT in (0.2, 2.0, 10.0, 30.0):
            try:
                a.update(CoolProp.PT_INPUTS, p, T + side * dT)
                return a.viscosity(), a.conductivity()
            except ValueError:
                continue
        raise ValueError(f"no transport properties for {self.key} at {p:.0f} Pa, {T:.1f} K")

    def _saturation(self, inputs: int, value: float) -> Saturation:
        liq = self._phase_props(inputs, value, 0.0)
        vap = self._phase_props(inputs, value, 1.0)
        return Saturation(
            T=vap[0], p=vap[1] if inputs == CoolProp.QT_INPUTS else value,
            h_l=liq[2], h_v=vap[2], rho_l=liq[3], rho_v=vap[3], mu_l=liq[4], mu_v=vap[4],
            k_l=liq[5], k_v=vap[5], cp_l=liq[6], cp_v=vap[6], T_l=liq[0],
        )

    @lru_cache(maxsize=4096)
    def sat_T(self, T: float) -> Saturation:
        return self._saturation(CoolProp.QT_INPUTS, T)

    def sat_p(self, p: float) -> Saturation:
        return self._sat_p(round(p, 1))

    @lru_cache(maxsize=4096)
    def _sat_p(self, p: float) -> Saturation:
        return self._saturation(CoolProp.PQ_INPUTS, p)

    def p_sat(self, T: float) -> float:
        """Saturation pressure (dew pressure for a pseudo-pure blend)."""
        return self.sat_T(T).p

    @lru_cache(maxsize=1024)
    def p_bubble(self, T: float) -> float:
        a = self._sat_as
        a.update(CoolProp.QT_INPUTS, 0.0, T)
        return a.p()

    def T_dew(self, p: float) -> float:
        return self.sat_p(p).T

    # ---- states -------------------------------------------------------------------

    def ph(self, p: float, h: float) -> State:
        if p < self.p_crit:
            s = self.sat_p(p)
            if s.h_l <= h <= s.h_v:
                x = (h - s.h_l) / s.h_fg
                rho = 1.0 / (x / s.rho_v + (1.0 - x) / s.rho_l)
                mu = 1.0 / (x / s.mu_v + (1.0 - x) / s.mu_l)
                k = x * s.k_v + (1.0 - x) * s.k_l
                cp = x * s.cp_v + (1.0 - x) * s.cp_l     # only used for reporting
                T = s.T_l + x * (s.T - s.T_l)            # glide of a zeotropic pseudo-pure blend
                return State(p, T, h, rho, mu, k, cp, x, s.T, "two-phase")
        a = self._as
        a.update(CoolProp.HmassP_INPUTS, h, p)
        return self._single_phase(p)

    def pt(self, p: float, T: float) -> State:
        a = self._as
        a.update(CoolProp.PT_INPUTS, p, T)
        return self._single_phase(p)

    def _single_phase(self, p: float) -> State:
        a = self._as
        T, h, rho, cp = a.T(), a.hmass(), a.rhomass(), a.cpmass()
        T_dew = self.T_dew(p) if p < self.p_crit else self.T_crit
        phase = "vapour" if T >= T_dew else "liquid"
        mu, k = self._transport(a, p, T, side=1.0 if phase == "vapour" else -1.0)
        return State(p, T, h, rho, mu, k, cp, None, T_dew, phase)

    def saturated_liquid(self, T: float) -> State:
        s = self.sat_T(T)
        return self.ph(s.p, s.h_l + 1e-6)

    def saturated_vapour(self, T: float) -> State:
        s = self.sat_T(T)
        return self.ph(s.p, s.h_v - 1e-6)

    def T_normal_boiling(self) -> float:
        return self.T_dew(P_ATM)

    def ideal_gas_cp_molar(self, T: float = 350.0) -> float:
        """Molar cp of the vapour at low pressure [J/(mol K)], used by the bed energy balance."""
        a = self._as
        a.update(CoolProp.PT_INPUTS, 0.2e5, T)
        return a.cpmass() * self.M


@lru_cache(maxsize=None)
def fluid(key: str) -> Fluid:
    return Fluid(key)


def components(key: str) -> dict[str, float]:
    """Mass fractions of the components of a blend, or {key: 1} for a single refrigerant."""
    b = materials.blends().get(key)
    if b is None:
        return {key: 1.0}
    total = sum(b.values())
    return {k: v / total for k, v in b.items()}


def mass_to_mole(mass_fractions: dict[str, float]) -> dict[str, float]:
    refs = materials.refrigerants()
    n = {k: w / refs[k].molar_mass for k, w in mass_fractions.items()}
    s = sum(n.values())
    return {k: v / s for k, v in n.items()}


def mole_to_mass(mole_fractions: dict[str, float]) -> dict[str, float]:
    refs = materials.refrigerants()
    m = {k: y * refs[k].molar_mass for k, y in mole_fractions.items()}
    s = sum(m.values())
    return {k: v / s for k, v in m.items()}


class Blend:
    """A true mixture of refrigerants (vapour-liquid equilibrium with composition)."""

    def __init__(self, names: tuple[str, ...]):
        self.names = names
        self._as = AbstractState("HEOS", "&".join(names))
        refs = materials.refrigerants()
        self.M = [refs[n].molar_mass / 1000.0 for n in names]   # kg/mol

    def _set(self, mass_fractions: dict[str, float]) -> None:
        self._as.set_mass_fractions([mass_fractions.get(n, 0.0) for n in self.names])

    def bubble(self, T: float, liquid: dict[str, float]) -> dict:
        """Bubble point of a liquid of given mass fractions: pressure, incipient vapour, latent heat."""
        a = self._as
        self._set(liquid)
        a.update(CoolProp.QT_INPUTS, 0.0, T)
        x = list(a.mole_fractions_liquid())
        y = list(a.mole_fractions_vapor())
        M_l = sum(xi * Mi for xi, Mi in zip(x, self.M))
        M_v = sum(yi * Mi for yi, Mi in zip(y, self.M))
        h_l = a.saturated_liquid_keyed_output(CoolProp.iHmolar) / M_l
        h_v = a.saturated_vapor_keyed_output(CoolProp.iHmolar) / M_v
        rho_l = a.saturated_liquid_keyed_output(CoolProp.iDmolar) * M_l
        rho_v = a.saturated_vapor_keyed_output(CoolProp.iDmolar) * M_v
        y_mass = mole_to_mass(dict(zip(self.names, y)))
        return {"p": a.p(), "vapour": y_mass, "h_fg": h_v - h_l, "rho_l": rho_l, "rho_v": rho_v}

    def dew_temperature(self, p: float, composition: dict[str, float]) -> float:
        a = self._as
        self._set(composition)
        a.update(CoolProp.PQ_INPUTS, p, 1.0)
        return a.T()

    def bubble_temperature(self, p: float, composition: dict[str, float]) -> float:
        a = self._as
        self._set(composition)
        a.update(CoolProp.PQ_INPUTS, p, 0.0)
        return a.T()


@lru_cache(maxsize=None)
def blend(names: tuple[str, ...]) -> Blend:
    return Blend(names)
