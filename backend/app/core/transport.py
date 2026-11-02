"""Equilibrium and mass transfer properties (thesis ch. 5)."""
import math

from .constants import K_B, N_A, R_UNIV, SH_A, SH_B, SH_C

ANGSTROM = 1e-10
METRE = 1.0
# The thesis spreadsheet converted the pore diameter with 1e-8 instead of 1e-10,
# which made D_K (and therefore D') ~100x too large. Kept only for "thesis" mode
# so the numbers in Tab. 8-11 can still be reproduced.
THESIS_PORE_SCALE = 1e-8


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
    d = molecule_size_a * ANGSTROM
    return 2.0 / 3.0 * math.sqrt(K_B * t / (math.pi * m)) * K_B * t / (math.pi * d**2 * p)


# rho D / mu for self-diffusion: 6/5 for rigid spheres, 6 A*/5 ~ 1.32 for Lennard-Jones gases
# (A* = Omega(2,2)/Omega(1,1) ~ 1.1 over the usual range of reduced temperatures)
CHAPMAN_ENSKOG_SELF = 1.32


def self_diffusivity(viscosity: float, rho: float) -> float:
    """Chapman-Enskog self-diffusion coefficient from the gas viscosity, D = 1.32 mu / rho [m2/s].

    Uses the measured viscosity instead of a hard-sphere molecule size, which is the least
    certain number in the kinetic-theory formula.
    """
    return CHAPMAN_ENSKOG_SELF * viscosity / rho


def knudsen_diffusivity(pore_diameter: float, molar_mass: float, t: float, scale: float = ANGSTROM) -> float:
    """DK = dp/3 * sqrt(8RT/(pi M))  [m2/s]. pore_diameter * scale is the diameter in metres."""
    dp = pore_diameter * scale
    return dp / 3.0 * math.sqrt(8.0 * R_UNIV * t / (math.pi * molar_mass))


def effective_diffusivity(d_mol: float, d_kn: float, tortuosity: float = 1.0) -> float:
    """Series resistances 1/D' = 1/D + 1/DK (Bosanquet), divided by the pore tortuosity factor."""
    return 1.0 / (1.0 / d_mol + 1.0 / d_kn) / tortuosity


def reynolds(w: float, length: float, rho: float, mu: float) -> float:
    return w * length * rho / mu


def schmidt(mu: float, d: float, rho: float) -> float:
    return mu / (d * rho)


def sherwood(re: float, sc: float) -> float:
    """Correlation used in the thesis: Sh = C Re^A Sc^B (Paderewski, 'ziarna', Re < 30)."""
    return SH_C * re**SH_A * sc**SH_B


def sherwood_wakao_funazkri(re_p: float, sc: float) -> float:
    """Wakao & Funazkri (1978), packed beds of spheres, Re_p based on superficial velocity and d_p."""
    return 2.0 + 1.1 * sc ** (1.0 / 3.0) * re_p**0.6


def film_coefficient(sh: float, d: float, length: float) -> float:
    """kc,g = Sh D / L  [m/s]."""
    return sh * d / length


def axial_dispersion(d_mol: float, u: float, d_particle: float) -> float:
    """Edwards & Richardson (1968): D_L = 0.73 Dm + 0.5 u dp / (1 + 9.49 Dm / (u dp)), u interstitial."""
    ud = u * d_particle
    return 0.73 * d_mol + 0.5 * ud / (1.0 + 9.49 * d_mol / ud)
