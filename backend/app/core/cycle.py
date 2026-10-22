"""
Two-bed adsorption cycle: pressure and temperature swing, non-isothermal, extended Langmuir, LDF.

Each bed is split into N cells along its height; x = 0 is the top (feed in, regenerate out) and
x = H the bottom (product out, purge in) - the usual counter-current arrangement. Per cell:

    adsorbed phase   dq_i/dt = k_i (q_i* - q_i),     k_i = 15 D'_i / R_p^2 (Glueckauf), D' from the
                                                      same molecular + Knudsen chain as the thesis
    gas phase        component balances with upwind convection between cells
    energy           (rho_b (c_s + sum q_i c_p,i) + wall + gas) dT/dt
                       = convection + sum dH_i rho_b dq_i/dt + U A (T_jacket - T)

The pressure is taken uniform along the bed (pressure drop through a slow-cycling bed is tiny next to
the swing) but changes in time. dP/dt follows from the global mass balance and the flow between
cells from the cell balances - no momentum equation needed.

Heat exchange with the jacket goes through the bed-to-wall film and the radial conduction of the
packing in series, U = 1 / (1/h_w + R_bed / (2.89 k_bed)); the second term is what limits large beds.

The two beds run the same step table, each in its own mode; they exchange no gas, only the
timing. A step can be ended by time (the pressure setpoint is then a controller target that limits
the filling or the evacuation, which is how a PIC on the line works) or by reaching its setpoint.
Cycles are repeated until the state at the start of a cycle stops changing (cyclic steady state).
"""
import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.integrate import solve_ivp

from . import fluids, isotherms, materials
from .constants import K_B, N_A

R = fluids.R_GAS
P_ATM = fluids.P_ATM

Mode = Literal["fill", "adsorb", "blowdown", "evacuate", "purge", "idle"]
MODES: tuple[str, ...] = ("fill", "adsorb", "blowdown", "evacuate", "purge", "idle")
Semantics = Literal["controller", "transition"]


@dataclass
class BedSpec:
    zeolite: str = "13X"
    diameter: float = 0.2          # m
    height: float = 1.0            # m
    wall: float = 0.005            # m, steel
    h_wall: float = 50.0           # W/(m2 K), bed-to-wall film
    k_bed: float = 0.2             # W/(m K), effective radial conductivity of the packing
    cp_solid: float = 920.0        # J/(kg K), zeolite
    tortuosity: float = 1.0
    cells: int = 16


@dataclass
class Plant:
    feed: dict[str, float] = field(default_factory=lambda: {"R32": 0.5, "R125": 0.5})  # mass fractions
    feed_T: float = 373.15             # K, gas at the adsorber inlet
    feed_pressure: float = 2.5e5       # Pa abs, reducer setting
    feed_flow: float = 10.0            # kg/h, flow controller limit
    product_pressure: float = P_ATM + 1.0e5   # Pa abs, back-pressure on the product line
    product_flow: float = 2.5          # kg/h, product recovery unit / valve fully open
    vacuum_speed: float = 15.0         # m3/h at suction, regenerate recovery unit / vacuum pump
    vacuum_ultimate: float = 0.1e5     # Pa abs, lowest pressure it reaches
    vacuum_max_flow: float = 20.0      # kg/h
    purge_gas: dict[str, float] | None = None   # mass fractions, default: the weakest-held component
    purge_flow: float = 0.3            # kg/h
    purge_T: float = 423.15            # K, after the purge heater
    purge_pressure: float = P_ATM + 5.0e5       # Pa abs, purge supply (reducer)
    jacket: dict[str, float | None] = field(default_factory=lambda: {
        "fill": 373.15, "adsorb": 373.15, "blowdown": 473.15, "evacuate": 473.15, "purge": 473.15, "idle": None,
    })
    T_amb: float = 293.15
    U_loss: float = 0.5                # W/(m2 K), insulated bed with the jacket off
    dp_full: float = 0.2e5             # Pa, valves pass their full flow above this difference
    T_condense: float = 308.15         # K, recovery units compress to p_sat at this temperature
    compressor_efficiency: float = 0.5


@dataclass
class Step:
    name: str
    duration: float                    # s
    bed_a: str
    bed_b: str
    control_bed: str | None = None     # "A" | "B" | None
    direction: str = ">"               # ">" pressurise up to, "<" evacuate down to
    setpoint: float | None = None      # Pa abs
    purge_pressure: float | None = None   # Pa abs, overrides Plant.purge_pressure in this step
    label: str = ""                    # optional short name shown in the step table


def barg(p_abs: float) -> float:
    return (p_abs - P_ATM) / 1e5


def from_barg(v: float) -> float:
    return v * 1e5 + P_ATM


# ---- one bed ------------------------------------------------------------------------------

class Bed:
    def __init__(self, spec: BedSpec, plant: Plant):
        self.spec, self.plant = spec, plant
        zeo = materials.zeolites()[spec.zeolite]
        refs = materials.refrigerants()

        self.names = list(plant.feed)
        self.nc = len(self.names)
        for n in self.names:
            if materials.adsorbed_amount(spec.zeolite, n) is None:
                raise ValueError(f"no adsorption data for {n} on {spec.zeolite}")
        self.iso = isotherms.Mixture(spec.zeolite, self.names)
        self.M = np.array([refs[n].molar_mass / 1000.0 for n in self.names])        # kg/mol
        self.cp = np.array([fluids.fluid(n).ideal_gas_cp_molar() for n in self.names])  # J/(mol K)
        self.dH = self.iso.dH

        y_feed = fluids.mass_to_mole(plant.feed)
        self.y_feed = np.array([y_feed[n] for n in self.names])
        # purge: the component the zeolite holds most weakly, unless given
        if plant.purge_gas:
            yp = fluids.mass_to_mole({n: plant.purge_gas.get(n, 0.0) for n in self.names})
            self.y_purge = np.array([yp[n] for n in self.names])
        else:
            strength = self.iso.q_m * self.iso.b_ref
            self.y_purge = np.eye(self.nc)[int(np.argmin(strength))]
        self.M_feed = float(self.y_feed @ self.M)
        self.M_purge = float(self.y_purge @ self.M)

        # geometry
        N = spec.cells
        self.N = N
        self.area = math.pi * spec.diameter**2 / 4.0
        self.V = self.area * spec.height
        self.Vc = self.V / N
        self.eps = zeo.bed_porosity
        self.rho_b = zeo.bulk_density
        self.mass_zeolite = self.rho_b * self.V
        self.Rp = zeo.grain_radius
        wall_mass = 7900.0 * math.pi * spec.diameter * spec.wall * spec.height
        self.C_wall = wall_mass * 500.0 / N                          # J/K per cell
        self.A_cell = math.pi * spec.diameter * spec.height / N       # wall area per cell
        self.U_jacket = 1.0 / (1.0 / spec.h_wall + (spec.diameter / 2.0) / (2.89 * spec.k_bed))

        # diffusion: D_m = cm T^1.5 / P, D_K = ck sqrt(T)  (corrected mode of the thesis chain)
        sizes = np.array([refs[n].molecule_size * 1e-10 for n in self.names])
        m_mol = self.M / N_A
        self.c_m = 2.0 / 3.0 * np.sqrt(K_B / (math.pi * m_mol)) * K_B / (math.pi * sizes**2)
        self.c_k = zeo.pore_diameter * 1e-10 / 3.0 * np.sqrt(8.0 * R / (math.pi * self.M))

        # molar flow limits
        self.n_feed = plant.feed_flow / 3600.0 / self.M_feed
        self.n_prod = plant.product_flow / 3600.0 / self.M_feed
        self.n_vac = plant.vacuum_max_flow / 3600.0 / self.M_feed
        self.n_purge = plant.purge_flow / 3600.0 / self.M_purge
        self.S = plant.vacuum_speed / 3600.0

        # state layout
        self.iq = slice(0, N * self.nc)
        self.iT = slice(N * self.nc, N * self.nc + N)
        self.iy = slice(N * self.nc + N, N * self.nc + N + N * (self.nc - 1))
        self.size = N * (2 * self.nc) + 1
        self.atol = np.concatenate([
            np.full(N * self.nc, 1e-6), np.full(N, 1e-3), np.full(N * (self.nc - 1), 1e-7), [1.0],
        ])

    @property
    def thermal_time_constant(self) -> float:
        """s, how fast the jacket can change the mean bed temperature."""
        heat_cap = self.rho_b * self.spec.cp_solid * self.V + self.C_wall * self.N
        return heat_cap / (self.U_jacket * math.pi * self.spec.diameter * self.spec.height)

    def clip_state(self, Y: np.ndarray) -> np.ndarray:
        Y = Y.copy()
        Y[self.iq] = np.clip(Y[self.iq], 0.0, np.tile(self.iso.q_m, self.N))
        jk = [v for v in self.plant.jacket.values() if v is not None] + [self.plant.feed_T, self.plant.T_amb]
        Y[self.iT] = np.clip(Y[self.iT], min(jk) - 30.0, max(jk) + 80.0)
        Y[self.iy] = np.clip(Y[self.iy], 0.0, 1.0)
        Y[-1] = max(Y[-1], 100.0)
        return Y

    def initial(self, T0: float, P0: float = 0.2e5) -> np.ndarray:
        y = np.zeros(self.size)
        y[self.iT] = T0
        y[self.iy] = np.tile(self.y_feed[:-1], self.N)
        y[-1] = P0
        return y

    # -- unpacking (works on (n,) and (n, K)) --
    def unpack(self, Y: np.ndarray):
        Y2 = Y if Y.ndim == 2 else Y[:, None]
        K = Y2.shape[1]
        N, nc = self.N, self.nc
        q = Y2[self.iq].reshape(N, nc, K)
        T = Y2[self.iT]
        yv = np.clip(Y2[self.iy].reshape(N, nc - 1, K), 0.0, 1.0)
        last = np.clip(1.0 - yv.sum(axis=1, keepdims=True), 0.0, 1.0)
        y = np.concatenate([yv, last], axis=1)
        y = y / y.sum(axis=1, keepdims=True)
        P = Y2[-1]
        return q, T, y, P

    # -- boundary devices --
    @staticmethod
    def _valve(dp, dp_full):
        s = 0.01 * dp_full
        return np.tanh(s * np.logaddexp(0.0, dp / s) / dp_full)

    def feed_header(self, P_beds: list, caps: list) -> list:
        """
        Split the feed between the beds that take it. One flow controller (limit n_feed) feeds a
        header; each bed takes gas from the header through its own inlet valve, closed by the bed's
        pressure controller as the bed approaches its setpoint (cap). The header pressure is solved
        so that what the controller passes equals what the beds take - a bed at low pressure (filling)
        draws most of it and starves the one already at adsorption pressure.
        """
        pl = self.plant
        if len(P_beds) == 1:
            # one bed: the inlet valve is oversized, the flow controller sets the flow
            P, c = np.asarray(P_beds[0], dtype=float), caps[0]
            supply = pl.feed_pressure if c is None else min(pl.feed_pressure, c)
            return [self.n_feed * self._valve(supply - P, pl.dp_full)]
        n_av = 3.0 * self.n_feed
        P = np.stack([np.asarray(x, dtype=float) for x in P_beds])            # (beds, K)
        cap = np.array([np.inf if c is None else c for c in caps])[:, None]
        lo = P.min(axis=0) - 1.0
        hi = np.full_like(lo, pl.feed_pressure)
        for _ in range(22):
            mid = 0.5 * (lo + hi)
            taken = n_av * self._valve(np.minimum(mid[None, :], cap) - P, pl.dp_full).sum(axis=0)
            excess = self.n_feed * self._valve(pl.feed_pressure - mid, pl.dp_full) - taken
            lo = np.where(excess > 0, mid, lo)
            hi = np.where(excess > 0, hi, mid)
        ph = 0.5 * (lo + hi)
        flows = n_av * self._valve(np.minimum(ph[None, :], cap) - P, pl.dp_full)
        return [flows[i] for i in range(len(P_beds))]

    def feed_cap(self, mode: str, ctrl: dict | None) -> float | None:
        return ctrl["setpoint"] if (ctrl and mode == "fill") else None

    def boundary(self, mode: str, P, T_top, ctrl: dict | None, purge_pressure: float, F_feed=None):
        """Molar flows (K,): F_top into the bed at the top, F_bot out of the bed at the bottom."""
        pl = self.plant
        zero = np.zeros_like(P)
        sp = ctrl["setpoint"] if ctrl else None
        if mode in ("fill", "adsorb"):
            F_top = F_feed if F_feed is not None else self.feed_header([P], [self.feed_cap(mode, ctrl)])[0]
            if mode == "adsorb":
                back = sp if ctrl else pl.product_pressure
                F_bot = self.n_prod * self._valve(P - back, pl.dp_full)
            else:
                F_bot = zero
            return F_top, F_bot
        if mode in ("blowdown", "evacuate", "purge"):
            floor = pl.vacuum_ultimate if not ctrl else max(pl.vacuum_ultimate, sp)
            s = 200.0
            n = self.S * s * np.logaddexp(0.0, (P - floor) / s) / (R * T_top)
            F_top = -self.n_vac * np.tanh(n / self.n_vac)
            F_bot = -self.n_purge * self._valve(purge_pressure - P, pl.dp_full) if mode == "purge" else zero
            return F_top, F_bot
        return zero, zero

    def jacket(self, mode: str) -> float | None:
        return self.plant.jacket.get(mode)

    # -- right-hand side --
    def rhs(self, Y: np.ndarray, mode: str, ctrl: dict | None, purge_pressure: float, F_feed=None) -> np.ndarray:
        one_d = Y.ndim == 1
        q, T, y, P = self.unpack(Y)
        N, nc = self.N, self.nc
        Vc, eps, rho_b = self.Vc, self.eps, self.rho_b
        P = np.maximum(P, 50.0)

        # equilibrium and kinetics
        p_bar = (y * P[None, None, :] / 1e5).transpose(0, 2, 1)            # (N, K, nc)
        q_star = self.iso.q_star(p_bar, T).transpose(0, 2, 1)               # (N, nc, K)
        Tn = T[:, None, :]
        d_m = self.c_m[None, :, None] * Tn**1.5 / P[None, None, :]
        d_k = self.c_k[None, :, None] * np.sqrt(Tn)
        k_ldf = 15.0 / self.Rp**2 / (1.0 / d_m + 1.0 / d_k) / self.spec.tortuosity
        qdot = k_ldf * (q_star - q)
        sq = qdot.sum(axis=1)                                                # (N, K)

        c = P[None, :] / (R * T)                                             # mol/m3
        cp_gas = np.einsum("nik,i->nk", y, self.cp)                          # J/(mol K)

        # boundaries
        F_top, F_bot = self.boundary(mode, P, T[0], ctrl, purge_pressure, F_feed)
        cp_feed = float(self.y_feed @ self.cp)
        cp_purge = float(self.y_purge @ self.cp)

        # heat capacity and sources
        C = Vc * rho_b * (self.spec.cp_solid + np.einsum("nik,i->nk", q, self.cp)) + self.C_wall + eps * Vc * c * cp_gas
        Tj = self.jacket(mode)
        if Tj is None:
            Q_wall = self.plant.U_loss * self.A_cell * (self.plant.T_amb - T)
        else:
            Q_wall = self.U_jacket * self.A_cell * (Tj - T)
        S = Vc * rho_b * np.einsum("nik,i->nk", qdot, self.dH) + Q_wall

        inv_RT = eps * Vc / (R * T)
        sum_inv = inv_RT.sum(axis=0)
        ads_total = (rho_b * Vc * sq).sum(axis=0)

        Tdot = np.zeros_like(T)
        for _ in range(2):
            temp_term = (eps * Vc * P[None, :] * Tdot / (R * T**2))
            Pdot = (F_top - F_bot - ads_total + temp_term.sum(axis=0)) / sum_inv
            acc = inv_RT * Pdot[None, :] - temp_term + rho_b * Vc * sq           # (N, K)
            faces = np.empty((N + 1, T.shape[1]))
            faces[0] = F_top
            faces[1:] = F_top[None, :] - np.cumsum(acc, axis=0)
            # convection: only inflowing streams change the cell temperature
            down = np.maximum(faces[:-1], 0.0)          # into cell k from above
            up = np.maximum(-faces[1:], 0.0)            # into cell k from below
            T_above = np.vstack([np.full((1, T.shape[1]), self.plant.feed_T), T[:-1]])
            T_below = np.vstack([T[1:], np.full((1, T.shape[1]), self.plant.purge_T)])
            cp_above = np.vstack([np.full((1, T.shape[1]), cp_feed), cp_gas[:-1]])
            cp_below = np.vstack([cp_gas[1:], np.full((1, T.shape[1]), cp_purge)])
            conv = down * cp_above * (T_above - T) + up * cp_below * (T_below - T)
            Tdot = (S + conv) / C

        # composition
        y_above = np.concatenate([np.broadcast_to(self.y_feed[None, :, None], (1, nc, T.shape[1])), y[:-1]], axis=0)
        y_below = np.concatenate([y[1:], np.broadcast_to(self.y_purge[None, :, None], (1, nc, T.shape[1]))], axis=0)
        ydot = (down[:, None, :] * (y_above - y) + up[:, None, :] * (y_below - y)
                - rho_b * Vc * (qdot - y * sq[:, None, :])) / (eps * Vc * c[:, None, :])

        out = np.concatenate([
            qdot.reshape(N * nc, -1),
            Tdot,
            ydot[:, : nc - 1, :].reshape(N * (nc - 1), -1),
            Pdot[None, :],
        ], axis=0)
        return out[:, 0] if one_d else out

    # -- derived quantities on a set of states --
    def sensors(self, Y: np.ndarray) -> dict:
        q, T, y, P = self.unpack(Y)
        idx = [self.N // 6, self.N // 2, (5 * self.N) // 6]
        return {
            "P": P,
            "T_top": T[idx[0]], "T_mid": T[idx[1]], "T_bottom": T[idx[2]], "T_mean": T.mean(axis=0),
            "q_mean": q.mean(axis=0),                         # (nc, K)
            "y_top": y[0], "y_bottom": y[-1],                 # (nc, K)
        }

    def inventory(self, Y: np.ndarray) -> np.ndarray:
        """mol of each component held by the bed (gas + adsorbed)."""
        q, T, y, P = self.unpack(Y)
        gas = (self.eps * self.Vc * (P[None, :] / (R * T))[:, None, :] * y).sum(axis=0)
        ads = (self.rho_b * self.Vc * q).sum(axis=0)
        return (gas + ads)[:, 0]


# ---- running the cycle ---------------------------------------------------------------------

@dataclass
class StepRecord:
    index: int
    name: str
    label: str
    t_start: float
    duration: float
    planned: float
    ended_by: str                        # "time" | "setpoint" | "immediate"
    control_bed: str | None
    setpoint: float | None
    t_reach: float | None                # s after step start when the controlled pressure got to the setpoint
    beds: dict[str, dict]


def _ctrl(step: Step, bed: str, semantics: Semantics) -> dict | None:
    if semantics != "controller" or step.control_bed != bed or step.setpoint is None:
        return None
    return {"setpoint": step.setpoint, "direction": step.direction}


def _integrate(bed: Bed, y0: np.ndarray, mode: str, ctrl: dict | None, purge_p: float, duration: float,
               event=None):
    if duration <= 0:
        return None
    return solve_ivp(lambda t, Y: bed.rhs(Y, mode, ctrl, purge_p), (0.0, duration), y0, method="BDF",
                     vectorized=True, rtol=1e-4, atol=bed.atol, dense_output=True, events=event)


FEED_MODES = ("fill", "adsorb")


def _integrate_pair(bed: Bed, yA: np.ndarray, yB: np.ndarray, modes: dict, ctrls: dict, purge_p: float,
                    duration: float, event=None):
    """Both beds take feed from the same header: integrate them as one system."""
    n = bed.size
    caps = [bed.feed_cap(modes["A"], ctrls["A"]), bed.feed_cap(modes["B"], ctrls["B"])]

    def fun(_t, Y):
        YA, YB = Y[:n], Y[n:]
        fa, fb = bed.feed_header([YA[-1], YB[-1]], caps)
        return np.concatenate([bed.rhs(YA, modes["A"], ctrls["A"], purge_p, fa),
                               bed.rhs(YB, modes["B"], ctrls["B"], purge_p, fb)], axis=0)

    atol = np.concatenate([bed.atol, bed.atol])
    return solve_ivp(fun, (0.0, duration), np.concatenate([yA, yB]), method="BDF", vectorized=True,
                     rtol=1e-4, atol=atol, dense_output=True, events=event)


def _step_samples(duration: float) -> np.ndarray:
    n = int(np.clip(duration / 10.0, 25, 180))
    return np.linspace(0.0, duration, n)


def _flows(bed: Bed, mode: str, ctrl, purge_p: float, Ys: np.ndarray, F_feed=None) -> dict:
    """Flows on sampled states (n, K): mol/s per component for each line, jacket heat W."""
    q, T, y, P = bed.unpack(Ys)
    F_top, F_bot = bed.boundary(mode, P, T[0], ctrl, purge_p, F_feed)
    feed = np.outer(bed.y_feed, np.maximum(F_top, 0.0))
    regen = y[0] * np.maximum(-F_top, 0.0)
    product = y[-1] * np.maximum(F_bot, 0.0)
    purge = np.outer(bed.y_purge, np.maximum(-F_bot, 0.0))
    Tj = bed.jacket(mode)
    if Tj is None:
        heat = bed.plant.U_loss * bed.A_cell * (bed.plant.T_amb - T)
    else:
        heat = bed.U_jacket * bed.A_cell * (Tj - T)
    heat = heat.sum(axis=0)
    # recovery-unit work: isothermal compression from P to the condensing pressure, / efficiency
    p_dis = fluids.fluid(_pseudo(bed.names)).p_sat(bed.plant.T_condense)
    n_regen = np.maximum(-F_top, 0.0)
    w_regen = n_regen * R * T[0] * np.log(np.maximum(p_dis / P, 1.0)) / bed.plant.compressor_efficiency
    n_prod = np.maximum(F_bot, 0.0)
    w_prod = n_prod * R * T[-1] * np.log(np.maximum(p_dis / P, 1.0)) / bed.plant.compressor_efficiency
    return {"feed": feed, "regen": regen, "product": product, "purge": purge, "heat": heat,
            "w_regen": w_regen, "w_product": w_prod, "F_top": F_top, "F_bot": F_bot}


def _pseudo(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    for key, comp in materials.blends().items():
        if set(comp) == set(names):
            return key
    return names[0]


def run(spec: BedSpec, plant: Plant, steps: list[Step], semantics: Semantics = "controller",
        max_cycles: int = 14, tol: float = 2e-3, accelerate: bool = True) -> dict:
    bed = Bed(spec, plant)
    T0 = plant.jacket.get(steps[0].bed_a) or plant.feed_T
    state = {"A": bed.initial(T0), "B": bed.initial(T0)}
    convergence: list[float] = []
    q_scale = float(bed.iso.q_m.max())
    record = None
    css = False
    last_jump = -10

    for cycle in range(max_cycles):
        start = {k: v.copy() for k, v in state.items()}
        inv_start = {k: bed.inventory(v[:, None]) for k, v in state.items()}
        steps_rec: list[StepRecord] = []
        series = {b: {k: [] for k in ("t", "P", "T_top", "T_mid", "T_bottom", "T_mean", "q_mean", "y_top", "y_bottom",
                                          "F_top", "F_bot", "heat")} for b in ("A", "B")}
        totals = {b: {k: np.zeros(bed.nc) for k in ("feed", "regen", "product", "purge")} | {"heat_in": 0.0, "heat_out": 0.0, "w_regen": 0.0, "w_product": 0.0}
                  for b in ("A", "B")}
        profiles = []
        t_now = 0.0

        for i, st in enumerate(steps):
            modes = {"A": st.bed_a, "B": st.bed_b}
            purge_p = st.purge_pressure if st.purge_pressure is not None else plant.purge_pressure
            ctrls = {b: _ctrl(st, b, semantics) for b in ("A", "B")}
            duration, ended_by = st.duration, "time"
            sols = {}

            shared = modes["A"] in FEED_MODES and modes["B"] in FEED_MODES
            n = bed.size
            event = None
            cb = st.control_bed
            if semantics == "transition" and cb and st.setpoint is not None:
                P0 = state[cb][-1]
                met = P0 > st.setpoint if st.direction == ">" else P0 < st.setpoint
                if met:
                    duration, ended_by = 0.0, "immediate"
                else:
                    # pressure is the last entry of a bed's state; bed B comes second in a joint system
                    idx = (2 * n - 1) if (shared and cb == "B") else (n - 1)

                    def event(_t, Y, sp=st.setpoint, idx=idx):
                        return Y[idx] - sp
                    event.terminal = True
                    event.direction = 1 if st.direction == ">" else -1

            if duration > 0 and shared:
                sol = _integrate_pair(bed, state["A"], state["B"], modes, ctrls, purge_p, duration, event)
                if event is not None and sol.status == 1 and len(sol.t_events[0]):
                    duration, ended_by = float(sol.t_events[0][0]), "setpoint"
                sols = {"pair": sol}
            elif duration > 0:
                if event is not None:
                    # a step ended by its setpoint: integrate the controlled bed first to find the end
                    sol = _integrate(bed, state[cb], modes[cb], None, purge_p, st.duration, event)
                    if sol.status == 1 and len(sol.t_events[0]):
                        duration, ended_by = float(sol.t_events[0][0]), "setpoint"
                    sols[cb] = sol
                for b in ("A", "B"):
                    if b not in sols:
                        sols[b] = _integrate(bed, state[b], modes[b], ctrls[b], purge_p, duration)

            bed_info = {}
            t_reach = None
            ts = _step_samples(duration) if duration > 0 else np.array([0.0])
            sampled = {}
            for b in ("A", "B"):
                if duration <= 0:
                    sampled[b] = state[b][:, None]
                elif shared:
                    if not sols["pair"].success:
                        raise RuntimeError(f"step {st.name}: {sols['pair'].message}")
                    Yp = sols["pair"].sol(ts)
                    sampled[b] = Yp[:n] if b == "A" else Yp[n:]
                else:
                    if not sols[b].success:
                        raise RuntimeError(f"step {st.name}, bed {b}: {sols[b].message}")
                    sampled[b] = sols[b].sol(ts)
            feeds = {"A": None, "B": None}
            if shared:
                fa, fb = bed.feed_header([sampled["A"][-1], sampled["B"][-1]],
                                         [bed.feed_cap(modes["A"], ctrls["A"]), bed.feed_cap(modes["B"], ctrls["B"])])
                feeds = {"A": fa, "B": fb}

            for b in ("A", "B"):
                Ys = sampled[b]
                sens = bed.sensors(Ys)
                fl = _flows(bed, modes[b], ctrls[b], purge_p, Ys, feeds[b])
                integ = (lambda a: np.trapezoid(a, ts, axis=-1)) if duration > 0 else (lambda a: np.zeros(a.shape[:-1]))
                moles = {k: integ(fl[k]) for k in ("feed", "regen", "product", "purge")}
                heat = fl["heat"]
                h_in = float(integ(np.maximum(heat, 0.0)))
                h_out = float(integ(np.maximum(-heat, 0.0)))
                for k in moles:
                    totals[b][k] += moles[k]
                totals[b]["heat_in"] += h_in
                totals[b]["heat_out"] += h_out
                totals[b]["w_regen"] += float(integ(fl["w_regen"]))
                totals[b]["w_product"] += float(integ(fl["w_product"]))

                series[b]["t"].append(t_now + ts)
                for k in ("P", "T_top", "T_mid", "T_bottom", "T_mean"):
                    series[b][k].append(sens[k])
                for k in ("q_mean", "y_top", "y_bottom"):
                    series[b][k].append(sens[k])
                series[b]["F_top"].append(fl["F_top"])
                series[b]["F_bot"].append(fl["F_bot"])
                series[b]["heat"].append(heat)

                if st.control_bed == b and st.setpoint is not None and duration > 0:
                    P = sens["P"]
                    reached = P >= st.setpoint - 0.01e5 if st.direction == ">" else P <= st.setpoint + 0.01e5
                    if reached.any():
                        t_reach = float(ts[int(np.argmax(reached))])

                kg = lambda v: {n: float(x * m) for n, x, m in zip(bed.names, v, bed.M)}
                bed_info[b] = {
                    "mode": modes[b],
                    "P_start": float(sens["P"][0]), "P_end": float(sens["P"][-1]),
                    "P_min": float(sens["P"].min()), "P_max": float(sens["P"].max()),
                    "T_start": float(sens["T_mean"][0]), "T_end": float(sens["T_mean"][-1]),
                    "q_start": [float(v) for v in sens["q_mean"][:, 0]],
                    "q_end": [float(v) for v in sens["q_mean"][:, -1]],
                    "feed_kg": kg(moles["feed"]), "product_kg": kg(moles["product"]),
                    "regen_kg": kg(moles["regen"]), "purge_kg": kg(moles["purge"]),
                    "heat_in_kWh": h_in / 3.6e6, "heat_out_kWh": h_out / 3.6e6,
                    "jacket_T": bed.jacket(modes[b]),
                }
                state[b] = Ys[:, -1].copy()

            q_end, T_end, _, _ = bed.unpack(state["A"][:, None])
            profiles.append({"q": q_end[:, :, 0].tolist(), "T": T_end[:, 0].tolist()})
            steps_rec.append(StepRecord(
                index=i + 1, name=st.name, label=st.label, t_start=t_now, duration=duration, planned=st.duration,
                ended_by=ended_by, control_bed=st.control_bed, setpoint=st.setpoint, t_reach=t_reach, beds=bed_info,
            ))
            t_now += duration

        # cyclic steady state check
        delta = 0.0
        for b in ("A", "B"):
            dq = np.abs(state[b][bed.iq] - start[b][bed.iq]).max() / q_scale
            dT = np.abs(state[b][bed.iT] - start[b][bed.iT]).max() / 10.0
            dP = abs(state[b][-1] - start[b][-1]) / 1e5
            delta = max(delta, dq, dT, dP)
        convergence.append(delta)
        inv_end = {k: bed.inventory(v[:, None]) for k, v in state.items()}
        record = (steps_rec, series, totals, profiles, inv_start, inv_end, t_now)
        if delta < tol and cycle >= 1:
            css = True
            break
        # The approach to the cyclic steady state is close to geometric (the slow part is the bed
        # temperature). Once the ratio between successive changes settles, jump ahead along the
        # last change - this roughly halves the number of cycles. The next cycle measures from the
        # extrapolated state, so a bad jump only costs an extra cycle.
        if accelerate and len(convergence) >= 3 and cycle - last_jump >= 2:
            r = convergence[-1] / convergence[-2]
            r_prev = convergence[-2] / convergence[-3]
            if 0.2 < r < 0.85 and abs(r - r_prev) < 0.25:
                factor = min(r / (1.0 - r), 3.0)
                for b in ("A", "B"):
                    state[b] = bed.clip_state(state[b] + factor * (state[b] - start[b]))
                last_jump = cycle

    steps_rec, series, totals, profiles, inv_start, inv_end, t_cycle = record
    return _report(bed, plant, steps, steps_rec, series, totals, profiles, inv_start, inv_end, t_cycle,
                   convergence, css, semantics)


# ---- report ----------------------------------------------------------------------------------

def _report(bed: Bed, plant: Plant, steps, steps_rec, series, totals, profiles, inv_start, inv_end, t_cycle,
            convergence, css, semantics) -> dict:
    names, M = bed.names, bed.M

    def cat(b, k):
        return np.concatenate(series[b][k], axis=-1)

    out_series = {"t": cat("A", "t").tolist()}
    for b in ("A", "B"):
        out_series[b] = {k: cat(b, k).tolist() for k in ("P", "T_top", "T_mid", "T_bottom", "T_mean", "heat")}
        out_series[b]["q_mean"] = {n: cat(b, "q_mean")[i].tolist() for i, n in enumerate(names)}
        out_series[b]["y_bottom"] = {n: cat(b, "y_bottom")[i].tolist() for i, n in enumerate(names)}
        out_series[b]["y_top"] = {n: cat(b, "y_top")[i].tolist() for i, n in enumerate(names)}
        out_series[b]["flow_in_top"] = (np.maximum(cat(b, "F_top"), 0) * bed.M_feed * 3600).tolist()
        out_series[b]["flow_out_top"] = (np.maximum(-cat(b, "F_top"), 0) * bed.M_feed * 3600).tolist()
        out_series[b]["flow_out_bottom"] = (np.maximum(cat(b, "F_bot"), 0) * bed.M_feed * 3600).tolist()

    # totals over both beds, kg
    tot = {k: sum(totals[b][k] for b in ("A", "B")) * M for k in ("feed", "regen", "product", "purge")}
    feed = tot["feed"]
    closure = []
    for b in ("A", "B"):
        t = totals[b]
        bal = t["feed"] + t["purge"] - t["regen"] - t["product"] - (inv_end[b] - inv_start[b])
        closure.append(float(np.abs(bal * M).sum() / max((t["feed"] * M).sum(), 1e-12)))

    strength = bed.iso.q_m * bed.iso.b_ref
    weak = int(np.argmin(strength))
    strong = int(np.argmax(strength))
    prod_total = tot["product"].sum()
    regen_net = tot["regen"] - tot["purge"]
    kpi = {
        "cycle_time_h": t_cycle / 3600.0,
        "feed_kg": float(feed.sum()),
        "feed_rate_kg_h": float(feed.sum() / max(t_cycle / 3600.0, 1e-9)),
        "product_kg": float(prod_total),
        "regen_kg": float(tot["regen"].sum()),
        "purge_kg": float(tot["purge"].sum()),
        "zeolite_kg": bed.mass_zeolite,
        "productivity": float(feed.sum() / (2 * bed.mass_zeolite) / max(t_cycle / 3600.0, 1e-9)),
        "heat_in_kWh": sum(totals[b]["heat_in"] for b in ("A", "B")) / 3.6e6,
        "heat_out_kWh": sum(totals[b]["heat_out"] for b in ("A", "B")) / 3.6e6,
        "compressor_kWh": sum(totals[b]["w_regen"] + totals[b]["w_product"] for b in ("A", "B")) / 3.6e6,
        "mass_balance_error": max(closure),
        "weak": names[weak], "strong": names[strong],
    }
    kpi["specific_energy_kWh_kg"] = (kpi["heat_in_kWh"] + kpi["compressor_kWh"]) / max(kpi["feed_kg"], 1e-9)
    if bed.nc > 1:
        kpi["product_purity"] = float(tot["product"][weak] / prod_total) if prod_total > 0 else None
        kpi["product_recovery"] = float(tot["product"][weak] / feed[weak]) if feed[weak] > 0 else None
        regen_pos = np.maximum(regen_net, 0.0)
        kpi["extract_purity"] = float(tot["regen"][strong] / tot["regen"].sum()) if tot["regen"].sum() > 0 else None
        kpi["extract_recovery"] = float(regen_pos[strong] / feed[strong]) if feed[strong] > 0 else None
        kpi["feed_composition"] = {n: float(v) for n, v in zip(names, plant.feed.values())}

    thermal = {
        "U_jacket": bed.U_jacket,
        "tau_h": bed.thermal_time_constant / 3600.0,
        "T_mean_min": float(np.min(out_series["A"]["T_mean"])),
        "T_mean_max": float(np.max(out_series["A"]["T_mean"])),
        "T_max": float(max(np.max(out_series[b][k]) for b in ("A", "B") for k in ("T_top", "T_mid", "T_bottom"))),
    }

    step_list = []
    for r in steps_rec:
        step_list.append({
            "index": r.index, "name": r.name, "label": r.label, "t_start": r.t_start, "duration": r.duration,
            "planned": r.planned, "ended_by": r.ended_by, "control_bed": r.control_bed,
            "setpoint_barg": barg(r.setpoint) if r.setpoint is not None else None,
            "t_reach": r.t_reach, "beds": r.beds,
        })

    result = {
        "components": names,
        "semantics": semantics,
        "steps": step_list,
        "series": out_series,
        "profiles": profiles,
        "kpi": kpi,
        "thermal": thermal,
        "convergence": convergence,
        "css": css,
        "cycles": len(convergence),
        "bed": {
            "volume_m3": bed.V, "zeolite_kg": bed.mass_zeolite, "cells": bed.N,
            "jacket_U": bed.U_jacket, "z": [(k + 0.5) / bed.N * bed.spec.height for k in range(bed.N)],
        },
    }
    result["findings"] = findings(bed, plant, steps, result)
    return result


def findings(bed: Bed, plant: Plant, steps: list[Step], res: dict) -> list[dict]:
    """Plain-language observations about the cycle, most important first."""
    out: list[dict] = []

    def add(severity: str, text: str, steps_: list[int] | None = None) -> None:
        out.append({"severity": severity, "steps": steps_ or [], "text": text})

    def listing(items: list[str]) -> str:
        return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1]

    p_floor = plant.vacuum_ultimate
    unreachable, not_reached, early = [], [], []
    for s in res["steps"]:
        idx, name = s["index"], s["name"]
        if s["control_bed"] is None or s["setpoint_barg"] is None:
            continue
        cb = s["control_bed"]
        info = s["beds"][cb]
        sp = from_barg(s["setpoint_barg"])
        evac = info["mode"] in ("blowdown", "evacuate", "purge")
        if s["ended_by"] == "immediate":
            add("warning", f"Step {idx} ({name}) ends the moment it starts: bed {cb} is already at "
                           f"{barg(info['P_start']):+.2f} bar g, past the step's setpoint {s['setpoint_barg']:+.2f} bar g. "
                           "Its condition or the previous step's condition needs to change.", [idx])
        elif evac and sp < p_floor:
            unreachable.append((idx, name, s["setpoint_barg"], barg(info["P_min"]), s["planned"]))
        elif s["t_reach"] is None:
            not_reached.append((idx, name, cb, s["setpoint_barg"], barg(info["P_end"]), s["duration"]))
        elif res["semantics"] == "controller" and s["t_reach"] < 0.4 * s["duration"]:
            early.append((idx, name, cb, s["t_reach"], s["duration"]))

    if unreachable:
        sp_text = listing(sorted({f"{u[2]:+.2f}" for u in unreachable}))
        add("warning",
            f"Steps {listing([str(u[0]) for u in unreachable])} wait for {sp_text} bar g, below the "
            f"{barg(p_floor):+.2f} bar g the vacuum source can reach. Their setpoints are never met, so they always "
            f"run to their full time ({sum(u[4] for u in unreachable):.0f} s per cycle); the bed bottoms out at "
            f"{listing([f'{u[3]:+.2f}' for u in unreachable])} bar g. Under end-on-setpoint logic they would hang until a timeout.",
            [u[0] for u in unreachable])
    if not_reached:
        parts = [f"{n[0]} ({n[3]:+.2f}, reached {n[4]:+.2f} bar g)" for n in not_reached]
        add("info", f"Setpoint not reached within the step time in step{'s' if len(parts) > 1 else ''} {listing(parts)}.",
            [n[0] for n in not_reached])
    for e in early:
        add("info", f"Step {e[0]} ({e[1]}): bed {e[2]} is at its setpoint after {e[3]:.0f} s of {e[4]:.0f} s and is held "
                    f"there for the rest; the step could be up to {e[4] - e[3]:.0f} s shorter.", [e[0]])

    # breakthrough into the product
    if bed.nc > 1:
        strong = res["kpi"]["strong"]
        hits, worst = [], 0.0
        for s in res["steps"]:
            for b, info in s["beds"].items():
                pk = info["product_kg"]
                tot = sum(pk.values())
                if info["mode"] == "adsorb" and tot > 1e-6 and pk[strong] / tot > 0.05:
                    hits.append(s["index"])
                    worst = max(worst, pk[strong] / tot)
        if hits:
            feed_share = plant.feed.get(strong, 0.0) / sum(plant.feed.values())
            add("warning", f"{strong} leaves with the product in step{'s' if len(hits) > 1 else ''} "
                           f"{listing([str(h) for h in sorted(set(hits))])}, up to {worst:.0%} of the product stream "
                           f"(feed: {feed_share:.0%}). The adsorption steps are long for this bed and feed; shorten them "
                           f"or lower the feed limit.", sorted(set(hits)))

    # desorption depth
    ads_end = des_end = None
    for s in res["steps"]:
        info = s["beds"]["A"]
        if info["mode"] in ("adsorb", "fill"):
            ads_end = info["q_end"]
        if info["mode"] in ("evacuate", "purge"):
            des_end = info["q_end"]
    if ads_end and des_end and sum(ads_end) > 0:
        loaded, left = sum(ads_end), sum(des_end)
        removed = 1.0 - left / loaded
        add("warning" if removed < 0.5 else "info",
            f"Regeneration takes {removed:.0%} of the loading off the bed ({loaded:.2f} -> {left:.2f} mol/kg on average). "
            "The rest stays on the zeolite and is carried round every cycle as dead capacity.")

    # thermal
    th = res["thermal"]
    jk = [v for v in plant.jacket.values() if v is not None]
    if len(jk) >= 2 and max(jk) - min(jk) > 20:
        swing = th["T_mean_max"] - th["T_mean_min"]
        jswing = max(jk) - min(jk)
        if swing < 0.5 * jswing:
            add("warning", f"The jacket swings {jswing:.0f} K, the bed only {swing:.0f} K. With D = {bed.spec.diameter:.2f} m the "
                           f"heat has to cross {bed.spec.diameter / 2 * 1000:.0f} mm of packing (U = {th['U_jacket']:.1f} W/m²K), "
                           f"so the bed's thermal time constant is {th['tau_h']:.1f} h against a "
                           f"{res['kpi']['cycle_time_h']:.1f} h cycle. Most of the regeneration is done by the vacuum; a "
                           "narrower bed, internal heat-exchange tubes or a hotter purge would make the heating count.")
    if th["T_max"] > 523.15:
        add("warning", f"The bed reaches {th['T_max'] - 273.15:.0f} °C. Check the temperature limit of the refrigerant on the "
                       "zeolite: some refrigerants decompose on hot zeolite.")

    if not res["css"]:
        add("info", f"No cyclic steady state after {res['cycles']} cycles (last change {res['convergence'][-1]:.1e}); "
                    "the numbers describe the last simulated cycle.")
    if res["kpi"]["mass_balance_error"] > 0.01:
        add("info", f"The mass balance closes to {res['kpi']['mass_balance_error']:.1%} only.")
    order = {"warning": 0, "info": 1}
    return sorted(out, key=lambda f: order[f["severity"]])

def presets() -> dict:
    import json
    with open(materials.DATA_DIR / "cycles.json", encoding="utf-8") as f:
        return json.load(f)["presets"]


def steps_from_table(rows: list[dict]) -> list[Step]:
    """Rows as in cycles.json (bar g) -> Step objects (Pa abs)."""
    out = []
    for r in rows:
        sp = r.get("setpoint")
        pp = r.get("purge_pressure")
        out.append(Step(
            name=r["name"], label=r.get("label", ""), duration=float(r["duration"]),
            bed_a=r["bed_a"], bed_b=r["bed_b"], control_bed=r.get("control"),
            direction=r.get("direction", ">"),
            setpoint=from_barg(sp) if sp is not None and r.get("control") else None,
            purge_pressure=from_barg(pp) if pp is not None else None,
        ))
    return out
