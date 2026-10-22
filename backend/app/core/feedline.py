"""
Feed line from the storage tank to the adsorber: pressure reducer + pipe segments that can be
heated or cooled.

    tank (saturated vapour or liquid) -> reducer (isenthalpic) -> segment 1 -> segment 2 -> ... -> adsorber

Along every segment the steady 1D energy and momentum balances are marched in the flow direction:

    m_dot dh/dz = q'(z)                       heat per metre from the jacket / trace / ambient
    dp/dz       = - f G^2 / (2 D rho)          homogeneous flow, Churchill friction factor

with the state (T, quality, rho, mu, k, cp) from CoolProp at (p, h). The heat flow per metre comes
from a series of resistances: inside film (correlations below), steel wall and the outside
(jacket fluid, insulation + air, or a fixed electric trace power).

Inside heat transfer coefficient:
  single phase   Gnielinski (Re > 3000), Hausen developing laminar flow (Re < 2300), blended between
  evaporation    Gungor & Winterton (1987), with the stratification correction for low Froude numbers
                 and a linear fade to the vapour coefficient above x = 0.9 (dry-out)
  condensation   Shah (1979)
"""
import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.integrate import solve_ivp

from . import fluids

G_ACC = 9.81
K_STEEL = 16.0          # W/(m K), stainless steel
H_AIR = 8.0             # W/(m2 K), natural convection + radiation outside

HeatingKind = Literal["medium", "trace", "insulated", "bare"]


@dataclass
class Heating:
    kind: HeatingKind = "insulated"
    T_medium: float = 363.15     # K, jacket fluid ("medium": hot or cold water in an annulus)
    h_medium: float = 1000.0     # W/(m2 K), jacket side coefficient
    q_trace: float = 0.0         # W/m, electric trace heating ("trace")
    insulation: float = 0.03     # m ("insulated", and around a trace)
    k_insulation: float = 0.04   # W/(m K)
    T_amb: float = 293.15        # K


@dataclass
class Segment:
    name: str
    D: float                     # m, inner diameter
    L: float                     # m
    wall: float = 0.002          # m, wall thickness
    roughness: float = 1.5e-5    # m, drawn stainless tube
    heating: Heating = field(default_factory=Heating)


@dataclass
class SegmentSummary:
    name: str
    z_start: float
    z_end: float
    T_in: float
    T_out: float
    x_in: float | None
    x_out: float | None
    duty: float                  # W, into the fluid (negative = cooling)
    dp: float                    # Pa, pressure loss including the inlet fitting
    residence: float             # s
    h_mean: float                # W/(m2 K), mean inside coefficient
    ntu: float | None            # single phase only: U A / (m_dot cp)
    re_in: float
    re_out: float
    velocity_in: float
    velocity_out: float
    wall_T_min: float            # K, inner wall
    wall_T_max: float


@dataclass
class LineResult:
    fluid: str
    mass_flow: float             # kg/h
    reducer: dict
    z: np.ndarray
    T: np.ndarray
    p: np.ndarray
    h: np.ndarray
    x: np.ndarray                # quality, nan outside the two-phase region
    T_dew: np.ndarray
    rho: np.ndarray
    mu: np.ndarray
    u: np.ndarray
    re: np.ndarray
    h_in: np.ndarray             # inside heat transfer coefficient
    q_lin: np.ndarray            # W/m into the fluid
    T_wall: np.ndarray
    T_outside: np.ndarray        # jacket / ambient temperature seen by the pipe
    segments: list[SegmentSummary]
    outlet: fluids.State
    warnings: list[str]

    @property
    def superheat(self) -> np.ndarray:
        return np.where(np.isnan(self.x), self.T - self.T_dew, 0.0)


# ---- correlations -------------------------------------------------------------------

def churchill(re: float, rel_rough: float) -> float:
    """Darcy friction factor, all regimes (Churchill 1977)."""
    re = max(re, 1e-3)
    a = (2.457 * math.log(1.0 / ((7.0 / re) ** 0.9 + 0.27 * rel_rough))) ** 16
    b = (37530.0 / re) ** 16
    return 8.0 * ((8.0 / re) ** 12 + 1.0 / (a + b) ** 1.5) ** (1.0 / 12.0)


def nusselt_single(re: float, pr: float, z_from_start: float, D: float) -> float:
    def laminar() -> float:
        gz = D * re * pr / max(z_from_start, 0.02)
        return 3.66 + 0.0668 * gz / (1.0 + 0.04 * gz ** (2.0 / 3.0))

    def turbulent(r: float) -> float:
        f = (0.79 * math.log(r) - 1.64) ** -2
        return (f / 8.0) * (r - 1000.0) * pr / (1.0 + 12.7 * math.sqrt(f / 8.0) * (pr ** (2.0 / 3.0) - 1.0))

    if re < 2300.0:
        return laminar()
    if re > 3000.0:
        return max(turbulent(re), laminar())
    s = (re - 2300.0) / 700.0
    return (1.0 - s) * laminar() + s * max(turbulent(3000.0), laminar())


def h_evaporation(G: float, x: float, D: float, sat: fluids.Saturation, q_flux: float) -> float:
    """Gungor & Winterton (1987) simplified flow boiling correlation."""
    x = min(max(x, 1e-4), 0.9)
    re_l = G * (1.0 - x) * D / sat.mu_l
    pr_l = sat.cp_l * sat.mu_l / sat.k_l
    h_l = max(0.023 * re_l**0.8 * pr_l**0.4, 3.66) * sat.k_l / D
    bo = abs(q_flux) / (G * sat.h_fg)
    e = 1.0 + 3000.0 * bo**0.86 + 1.12 * (x / (1.0 - x)) ** 0.75 * (sat.rho_l / sat.rho_v) ** 0.41
    fr = G**2 / (sat.rho_l**2 * G_ACC * D)
    if fr < 0.05:
        e *= fr ** (0.1 - 2.0 * fr)
    return e * h_l


def h_condensation(G: float, x: float, D: float, sat: fluids.Saturation, p_crit: float) -> float:
    """Shah (1979)."""
    x = min(max(x, 1e-4), 0.999)
    re_lo = G * D / sat.mu_l
    pr_l = sat.cp_l * sat.mu_l / sat.k_l
    h_lo = max(0.023 * re_lo**0.8 * pr_l**0.4, 3.66) * sat.k_l / D
    pr = sat.p / p_crit
    return h_lo * ((1.0 - x) ** 0.8 + 3.8 * x**0.76 * (1.0 - x) ** 0.04 / pr**0.38)


# ---- the march --------------------------------------------------------------------------

class _Pipe:
    """Heat flow per metre and inside coefficient for one segment at a given fluid state."""

    def __init__(self, seg: Segment, fl: fluids.Fluid, m_dot: float):
        self.seg, self.fl, self.m_dot = seg, fl, m_dot
        self.area = math.pi * seg.D**2 / 4.0
        self.G = m_dot / self.area
        self.D_out = seg.D + 2.0 * seg.wall
        # resistances per metre of pipe, K m / W
        self.r_wall = math.log(self.D_out / seg.D) / (2.0 * math.pi * K_STEEL)
        h = seg.heating
        if h.kind == "medium":
            self.r_out = 1.0 / (math.pi * self.D_out * h.h_medium)
            self.T_out = h.T_medium
        elif h.kind == "insulated":
            d_ins = self.D_out + 2.0 * h.insulation
            self.r_out = math.log(d_ins / self.D_out) / (2.0 * math.pi * h.k_insulation) + 1.0 / (math.pi * d_ins * H_AIR)
            self.T_out = h.T_amb
        elif h.kind == "bare":
            self.r_out = 1.0 / (math.pi * self.D_out * H_AIR)
            self.T_out = h.T_amb
        else:  # trace: fixed power, the insulation keeps it in
            self.r_out = math.inf
            self.T_out = h.T_amb

    def inside(self, st: fluids.State, z_local: float, q_guess: float) -> float:
        D, G = self.seg.D, self.G
        if st.phase == "two-phase":
            sat = self.fl.sat_p(st.p)
            if q_guess >= 0.0:
                h_tp = h_evaporation(G, st.x, D, sat, q_guess)
                if st.x > 0.9:
                    re_v = G * D / sat.mu_v
                    h_v = nusselt_single(re_v, sat.cp_v * sat.mu_v / sat.k_v, z_local, D) * sat.k_v / D
                    s = (st.x - 0.9) / 0.1
                    return (1.0 - s) * h_tp + s * h_v
                return h_tp
            return h_condensation(G, st.x, D, sat, self.fl.p_crit)
        re = G * D / st.mu
        pr = st.cp * st.mu / st.k
        return nusselt_single(re, pr, z_local, D) * st.k / D

    def heat(self, st: fluids.State, z_local: float) -> tuple[float, float]:
        """(q' into the fluid [W/m], inside coefficient)."""
        if self.seg.heating.kind == "trace":
            q = self.seg.heating.q_trace
            return q, self.inside(st, z_local, q / (math.pi * self.seg.D))
        q = 0.0
        h_i = 1.0
        for _ in range(3):   # the boiling coefficient depends on the heat flux
            h_i = self.inside(st, z_local, q / (math.pi * self.seg.D))
            r = 1.0 / (math.pi * self.seg.D * h_i) + self.r_wall + self.r_out
            q = (self.T_out - st.T) / r
        return q, h_i


def simulate(fluid_key: str, mass_flow: float, p_tank: float, h_tank: float, p_reducer: float,
             segments: list[Segment], points_per_segment: int = 80) -> LineResult:
    """mass_flow in kg/h, pressures in Pa, h_tank = specific enthalpy of what leaves the tank."""
    fl = fluids.fluid(fluid_key)
    m_dot = mass_flow / 3600.0
    warnings: list[str] = []

    if p_reducer >= p_tank:
        warnings.append(
            f"The tank pressure ({p_tank / 1e5:.2f} bar) is not above the reducer setting "
            f"({p_reducer / 1e5:.2f} bar), so the reducer cannot hold its outlet pressure."
        )
        p_reducer = p_tank * 0.98
    after = fl.ph(p_reducer, h_tank)
    reducer = {
        "p_in": p_tank, "p_out": p_reducer, "T_in": fl.ph(p_tank, h_tank).T, "T_out": after.T,
        "x_out": after.x, "phase_out": after.phase,
    }

    cols = {k: [] for k in ("z", "T", "p", "h", "x", "T_dew", "rho", "mu", "u", "re", "h_in", "q", "T_wall", "T_out")}
    summaries: list[SegmentSummary] = []
    p, h, z0 = p_reducer, h_tank, 0.0
    prev_area = None

    for seg in segments:
        pipe = _Pipe(seg, fl, m_dot)
        # inlet fitting: sudden expansion or contraction, on the smaller pipe's velocity head
        dp_fitting = 0.0
        if prev_area is not None and abs(prev_area - pipe.area) > 1e-12:
            st = fl.ph(p, h)
            small, large = min(prev_area, pipe.area), max(prev_area, pipe.area)
            u_small = m_dot / (st.rho * small)
            k = (1.0 - small / large) ** 2 if pipe.area > prev_area else 0.5 * (1.0 - small / large)
            dp_fitting = k * st.rho * u_small**2 / 2.0
            p -= dp_fitting
        prev_area = pipe.area

        def rhs(z: float, y: np.ndarray, pipe=pipe) -> list[float]:
            st = fl.ph(y[1], y[0])
            q, _ = pipe.heat(st, z)
            re = pipe.G * pipe.seg.D / st.mu
            f = churchill(re, pipe.seg.roughness / pipe.seg.D)
            return [q / m_dot, -f * pipe.G**2 / (2.0 * pipe.seg.D * st.rho)]

        try:
            sol = solve_ivp(rhs, (0.0, seg.L), [h, p], method="RK45", rtol=1e-7, atol=[1e-2, 1e-2],
                            max_step=seg.L / 40.0, dense_output=True)
        except ValueError as e:
            if "out of range" not in str(e):
                raise
            raise ValueError(f"{seg.name}: the gas would get hotter than the property data for {fluid_key} reach "
                             f"(about {fl._as.Tmax() - 273.15:.0f} °C). Less heat or more flow.") from None
        zs = np.linspace(0.0, seg.L, points_per_segment)
        hs, ps = sol.sol(zs)

        seg_rows = []
        for zl, hl, pl in zip(zs, hs, ps):
            st = fl.ph(pl, hl)
            q, h_i = pipe.heat(st, zl)
            u = m_dot / (st.rho * pipe.area)
            t_wall = st.T + q / (math.pi * seg.D * h_i)
            seg_rows.append((st, q, h_i, u, t_wall))
            cols["z"].append(z0 + zl)
            cols["T"].append(st.T)
            cols["p"].append(pl)
            cols["h"].append(hl)
            cols["x"].append(st.x if st.x is not None else np.nan)
            cols["T_dew"].append(st.T_dew)
            cols["rho"].append(st.rho)
            cols["mu"].append(st.mu)
            cols["u"].append(u)
            cols["re"].append(pipe.G * seg.D / st.mu)
            cols["h_in"].append(h_i)
            cols["q"].append(q)
            cols["T_wall"].append(t_wall)
            cols["T_out"].append(pipe.T_out)

        st_in, st_out = seg_rows[0][0], seg_rows[-1][0]
        h_mean = float(np.mean([r[2] for r in seg_rows]))
        ntu = None
        if st_in.phase != "two-phase" and st_out.phase != "two-phase" and seg.heating.kind != "trace":
            u_overall = 1.0 / (1.0 / (math.pi * seg.D * h_mean) + pipe.r_wall + pipe.r_out)
            ntu = u_overall * seg.L / (m_dot * 0.5 * (st_in.cp + st_out.cp))
        summaries.append(SegmentSummary(
            name=seg.name, z_start=z0, z_end=z0 + seg.L, T_in=st_in.T, T_out=st_out.T,
            x_in=st_in.x, x_out=st_out.x, duty=m_dot * (hs[-1] - hs[0]),
            dp=dp_fitting + (ps[0] - ps[-1]),
            residence=float(np.trapezoid(1.0 / np.array([r[3] for r in seg_rows]), zs)),
            h_mean=h_mean, ntu=ntu,
            re_in=pipe.G * seg.D / st_in.mu, re_out=pipe.G * seg.D / st_out.mu,
            velocity_in=seg_rows[0][3], velocity_out=seg_rows[-1][3],
            wall_T_min=min(r[4] for r in seg_rows), wall_T_max=max(r[4] for r in seg_rows),
        ))

        # condensation on a cold wall while the bulk is still superheated
        for st, q, _, _, t_wall in seg_rows:
            if st.phase == "vapour" and q < 0 and t_wall < st.T_dew:
                warnings.append(
                    f"{seg.name}: the wall is below the dew point ({t_wall - 273.15:.0f} °C vs "
                    f"{st.T_dew - 273.15:.0f} °C), refrigerant condenses on it while the gas is still superheated."
                )
                break

        h, p, z0 = float(hs[-1]), float(ps[-1]), z0 + seg.L

    out = fl.ph(p, h)
    arr = {k: np.array(v) for k, v in cols.items()}
    return LineResult(
        fluid=fluid_key, mass_flow=mass_flow, reducer=reducer,
        z=arr["z"], T=arr["T"], p=arr["p"], h=arr["h"], x=arr["x"], T_dew=arr["T_dew"], rho=arr["rho"],
        mu=arr["mu"], u=arr["u"], re=arr["re"], h_in=arr["h_in"], q_lin=arr["q"], T_wall=arr["T_wall"],
        T_outside=arr["T_out"], segments=summaries, outlet=out, warnings=warnings,
    )


def solve_setting(fluid_key: str, mass_flow: float, p_tank: float, h_tank: float, p_reducer: float,
                  segments: list[Segment], index: int, target_T: float,
                  lo: float, hi: float, tol: float = 0.05) -> tuple[float, LineResult, bool]:
    """
    Find the jacket temperature (kind "medium") or trace power (kind "trace") of segments[index]
    that brings the outlet to target_T. Returns (value, result, reached). The outlet temperature
    rises monotonically with both, so bisection is enough.
    """
    seg = segments[index]
    attr = "q_trace" if seg.heating.kind == "trace" else "T_medium"

    def run(v: float) -> LineResult | None:
        setattr(seg.heating, attr, v)
        try:
            return simulate(fluid_key, mass_flow, p_tank, h_tank, p_reducer, segments)
        except ValueError:
            return None          # so much heat that the gas leaves the property range: "too hot"

    def t_out(r: LineResult | None) -> float:
        return math.inf if r is None else r.outlet.T

    r_lo = run(lo)
    if r_lo is None:
        raise ValueError("even the lowest setting overheats the gas")
    if r_lo.outlet.T >= target_T:
        return lo, r_lo, abs(r_lo.outlet.T - target_T) < 1.0
    r_hi = run(hi)
    if r_hi is not None and r_hi.outlet.T <= target_T:
        return hi, r_hi, abs(r_hi.outlet.T - target_T) < 1.0
    a, b = lo, hi
    best, best_v = r_lo, lo
    for _ in range(40):
        mid = 0.5 * (a + b)
        res = run(mid)
        if res is not None:
            best, best_v = res, mid
            if abs(res.outlet.T - target_T) < tol:
                return mid, res, True
        if t_out(res) < target_T:
            a = mid
        else:
            b = mid
    setattr(seg.heating, attr, best_v)
    return best_v, best, abs(best.outlet.T - target_T) < 1.0
