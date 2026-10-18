"""
Rosen solution for a fixed bed with intraparticle diffusion + external film,
linear isotherm. Asymptotic (erf) form, valid for large lambda':

    c/c0 = 1/2 [1 + erf(E)],   E = (3 tau' / (2 lambda') - 1) / (2 sqrt((1 + 5 psi) / (5 lambda')))
    tau' = 2 D' / R^2 (t - H/w)
"""
import math

import numpy as np
from scipy.special import erf, erfinv


def parameters(d_eff: float, ka: float, height: float, z: float, w: float, radius: float, kcg: float) -> tuple[float, float]:
    """Length parameter lambda' and mass transfer resistance parameter psi."""
    lam = 3.0 * d_eff * ka * height / (z * w * radius**2)
    psi = d_eff * ka / (radius * kcg)
    return lam, psi


def spread(lam: float, psi: float) -> float:
    return math.sqrt((1.0 + 5.0 * psi) / (5.0 * lam))


def e_for_threshold(threshold: float) -> float:
    """Inverse of c/c0 = (1 + erf E)/2. Replaces the lookup table (Tab. 12) used in v0.0.1."""
    return float(erfinv(2.0 * threshold - 1.0))


def breakthrough_time(threshold: float, lam: float, psi: float, d_eff: float, radius: float, height: float, w: float) -> float:
    e = e_for_threshold(threshold)
    tau_p = 2.0 / 3.0 * lam * (1.0 + 2.0 * e * spread(lam, psi))
    tau_p = max(tau_p, 0.0)
    return radius**2 / (2.0 * d_eff) * tau_p + height / w


def stoichiometric_time(lam: float, d_eff: float, radius: float, height: float, w: float) -> float:
    """c/c0 = 0.5 point (tau' = 2/3 lambda')."""
    return radius**2 * lam / (3.0 * d_eff) + height / w


def curve(lam: float, psi: float, d_eff: float, radius: float, height: float, w: float,
          n: int = 300, t_max: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Breakthrough curve c/c0(t) up to t_max (default 1.6 t_stoich). Points are denser around the front."""
    t_s = stoichiometric_time(lam, d_eff, radius, height, w)
    t_max = t_max or 1.6 * t_s
    sig = spread(lam, psi) * (t_s - height / w)
    coarse = np.linspace(0.0, t_max, n // 2)
    fine = np.linspace(max(0.0, t_s - 5 * sig), min(t_max, t_s + 5 * sig), n - n // 2)
    t = np.unique(np.concatenate([coarse, fine]))

    tau_p = 2.0 * d_eff / radius**2 * (t - height / w)
    e = (3.0 * tau_p / (2.0 * lam) - 1.0) / (2.0 * spread(lam, psi))
    c = 0.5 * (1.0 + erf(e))
    c[t < height / w] = 0.0
    return t, c
