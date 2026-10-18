"""
Numerical fixed-bed model: linear driving force (LDF) + axial dispersion,
solved with the method of lines. Used to check the Rosen approximation and to get
concentration profiles inside the bed (the Rosen solution only gives the outlet).

Dimensionless form (zeta = x/H, theta = t w/H, c and q scaled by c0 and Ka*c0):

    dc/dtheta = -dc/dzeta + 1/Pe d2c/dzeta2 - kappa dq/dtheta
    dq/dtheta = St (c - q)                       linear isotherm, q* = c

    kappa = Ka / z,   St = k_LDF H / w,   k_LDF = 15 D' / (R^2 (1 + 5 psi))

15 D'/R^2 is Glueckauf's LDF approximation of diffusion in a sphere, (1 + 5 psi) adds the
external film in series - with these the LDF model has exactly the same second moment as
the Rosen solution, so for Pe -> inf both should give the same front.

Discretisation: finite volumes, Danckwerts inlet, zero-gradient outlet, Koren flux
limiter for convection (2nd order, no wiggles at the front), LSODA with a banded Jacobian.
"""
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .pipeline import Bed


@dataclass
class LdfSolution:
    t: np.ndarray              # s
    c_out: np.ndarray          # c/c0 at the outlet
    zeta: np.ndarray           # x/H of the profile points
    t_profiles: np.ndarray     # s
    c_profiles: np.ndarray     # (len(t_profiles), len(zeta)) gas phase c/c0
    q_profiles: np.ndarray     # same shape, loading q/q*(c0)
    kappa: float
    stanton: float
    peclet: float
    n_cells: int
    n_rhs: int

    def time_at(self, threshold: float) -> float | None:
        """First time the outlet reaches c/c0 = threshold (linear interpolation)."""
        idx = np.nonzero(self.c_out >= threshold)[0]
        if len(idx) == 0:
            return None
        i = idx[0]
        if i == 0:
            return float(self.t[0])
        t0, t1 = self.t[i - 1], self.t[i]
        c0, c1 = self.c_out[i - 1], self.c_out[i]
        return float(t0 + (threshold - c0) * (t1 - t0) / (c1 - c0))


def _koren(r: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, np.minimum(2.0 * r, np.minimum((1.0 + 2.0 * r) / 3.0, 2.0)))


def _rhs_factory(n: int, kappa: float, st: float, pe: float):
    dz = 1.0 / n
    inv_pe = 1.0 / pe
    flux = np.empty(n + 1)
    counter = {"n": 0}

    def rhs(_theta: float, y: np.ndarray) -> np.ndarray:
        counter["n"] += 1
        c = y[0::2]
        q = y[1::2]

        # faces k = 1..n-1 sit between cells k-1 (upwind) and k
        cu = c[:-1]
        cprev = np.concatenate(([1.0], c[:-2]))   # cell before the upwind one, inlet ghost = 1
        cnext = c[1:]
        back = cu - cprev
        fwd = cnext - cu
        small = np.abs(back) < 1e-12
        r = np.where(small, 0.0, fwd / np.where(small, 1.0, back))
        c_face = cu + 0.5 * _koren(r) * back

        flux[0] = 1.0                                  # Danckwerts: total inlet flux = w c0
        flux[1:n] = c_face - inv_pe * fwd / dz
        flux[n] = c[-1]                                # outlet, dc/dzeta = 0

        dq = st * (c - q)
        out = np.empty_like(y)   # fresh array - stiff solvers keep references to old f values
        out[0::2] = -(flux[1:] - flux[:-1]) / dz - kappa * dq
        out[1::2] = dq
        return out

    return rhs, counter


def solve(kappa: float, stanton: float, peclet: float, t_ref: float, t_end: float,
          n_cells: int = 200, n_out: int = 400, n_profiles: int = 80, profile_points: int = 60,
          rtol: float = 1e-5, atol: float = 1e-9) -> LdfSolution:
    rhs, counter = _rhs_factory(n_cells, kappa, stanton, peclet)
    theta_end = t_end / t_ref

    theta_out = np.linspace(0.0, theta_end, n_out)
    theta_prof = np.linspace(0.0, theta_end, n_profiles)
    theta_eval = np.unique(np.concatenate([theta_out, theta_prof]))

    sol = solve_ivp(
        rhs, (0.0, theta_end), np.zeros(2 * n_cells), method="LSODA",
        t_eval=theta_eval, lband=4, uband=2, rtol=rtol, atol=atol,
    )
    if not sol.success:
        raise RuntimeError(f"LDF solver failed: {sol.message}")

    c_all = sol.y[0::2].T
    q_all = sol.y[1::2].T
    out_idx = np.searchsorted(theta_eval, theta_out)
    prof_idx = np.searchsorted(theta_eval, theta_prof)
    cells = np.linspace(0, n_cells - 1, profile_points).round().astype(int)

    return LdfSolution(
        t=theta_out * t_ref,
        c_out=np.clip(c_all[out_idx, -1], 0.0, 1.0),
        zeta=(cells + 0.5) / n_cells,
        t_profiles=theta_prof * t_ref,
        c_profiles=np.clip(c_all[np.ix_(prof_idx, cells)], 0.0, 1.0),
        q_profiles=np.clip(q_all[np.ix_(prof_idx, cells)], 0.0, 1.0),
        kappa=kappa,
        stanton=stanton,
        peclet=peclet,
        n_cells=n_cells,
        n_rhs=counter["n"],
    )


def simulate(bed: Bed, t_end: float | None = None, **kwargs) -> LdfSolution:
    """Run the LDF model for a bed from pipeline.run(). Default horizon = 1.6 x t_stoich."""
    t_stoich = bed.t_ref * (1.0 + bed.kappa)
    return solve(
        kappa=bed.kappa,
        stanton=bed.k_ldf * bed.t_ref,
        peclet=bed.peclet,
        t_ref=bed.t_ref,
        t_end=t_end or 1.6 * t_stoich,
        **kwargs,
    )
