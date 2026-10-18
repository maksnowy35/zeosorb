"""Equilibrium and mass transfer properties (thesis ch. 5)."""
import math

from .constants import K_B, N_A, R_UNIV, SH_A, SH_B, SH_C


def gas_density(molar_mass: float, p: float, t: float) -> float:
    """Ideal gas density = equilibrium concentration c* [kg/m3]."""
    return p * molar_mass / (R_UNIV * t)


def henry_constant(q: float, bulk_density: float, molar_mass: float, c_star: float) -> tuple[float, float]:
    """Ka = av / c*,  av = q * rho_bulk * M [kg/m3 of bed]."""
    av = q * bulk_density * molar_mass / 1000.0
    return av / c_star, av


def molecular_diffusivity(molecule_size_a: float, molar_mass: float, p: float, t: float) -> float:
    """Kinetic theory of gases: D = 2/3 sqrt(kT/(pi m)) kT/(pi d^2 p)  [m2/s]."""
    m = molar_mass / 1000.0 / N_A
    d = molecule_size_a * 1e-10
    return 2.0 / 3.0 * math.sqrt(K_B * t / (math.pi * m)) * K_B * t / (math.pi * d**2 * p)


def knudsen_diffusivity(pore_diameter_a: float, molar_mass: float, t: float) -> float:
    """DK = dp/3 * sqrt(8RT/(pi M))  [m2/s]."""
    dp = pore_diameter_a * 1e-8  # A -> m
    return dp / 3.0 * math.sqrt(8.0 * R_UNIV * t / (math.pi * molar_mass))


def effective_diffusivity(d_mol: float, d_kn: float) -> float:
    """Series resistances: 1/D' = 1/D + 1/DK."""
    return 1.0 / (1.0 / d_mol + 1.0 / d_kn)


def reynolds(w: float, length: float, rho: float, mu: float) -> float:
    return w * length * rho / mu


def schmidt(mu: float, d: float, rho: float) -> float:
    return mu / (d * rho)


def sherwood(re: float, sc: float) -> float:
    return SH_C * re**SH_A * sc**SH_B


def film_coefficient(sh: float, d: float, length: float) -> float:
    """kc,g = Sh D / dz  [m/s]."""
    return sh * d / length
