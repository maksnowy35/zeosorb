"""
Two-phase storage tank (liquid + vapour under its own pressure) feeding the process.

Lumped model: liquid, vapour and steel wall share one temperature, the pressure is the
saturation (bubble) pressure at that temperature. Drawing refrigerant off the tank costs heat:

  vapour withdrawal  every kg leaving has to be evaporated inside the tank -> m h_fg of cooling,
                     the tank cools down and its pressure falls;
  liquid withdrawal  only the vapour that refills the freed volume evaporates (rho_v / rho_l of it).

    (m_l c_l + m_w c_w) dT/dt = - m_dot * dh_eff + UA (T_amb - T) + Q_heater

For a zeotropic blend the vapour is richer in the volatile components than the liquid, so vapour
withdrawal also shifts the composition of the feed and of what stays in the tank (fractionation).
The liquid is assumed to hold almost all of the mass (bubble-point approximation), which is fine
until the tank is nearly empty.
"""
import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.integrate import solve_ivp

from . import fluids

Withdrawal = Literal["vapour", "liquid"]
Heater = Literal["off", "thermostat", "power"]

STEEL_CP = 500.0      # J/(kg K)
ASPECT = 2.8          # L / D of a horizontal ton tank


@dataclass
class TankInput:
    fluid: str = "R410A"
    volume: float = 1.0                 # m3 water capacity
    fill_mass: float = 800.0            # kg at the start
    T0: float = 293.15                  # K
    T_amb: float = 293.15               # K
    U_amb: float = 8.0                  # W/(m2 K), bare steel: natural convection + radiation
    wall_mass: float = 400.0            # kg of steel
    withdrawal: Withdrawal = "vapour"
    heater: Heater = "off"
    heater_T_set: float = 293.15        # K (thermostat)
    heater_power: float = 3000.0        # W (max power for the thermostat, fixed power otherwise)
    mass_flow: float = 30.0             # kg/h
    duration: float = 8.0               # h
    p_min: float | None = None          # Pa, lowest tank pressure the reducer still works with


@dataclass
class TankResult:
    t: np.ndarray            # h
    T: np.ndarray            # K
    p: np.ndarray            # Pa
    mass: np.ndarray         # kg
    liquid_fraction: np.ndarray   # liquid volume / tank volume
    q_heater: np.ndarray     # W
    q_ambient: np.ndarray    # W
    feed_composition: list[dict[str, float]]    # mass fractions of what leaves the tank
    liquid_composition: list[dict[str, float]]
    t_pressure_low: float | None    # h, when p dropped below p_min
    t_empty: float | None           # h, when the liquid ran out
    warnings: list[str] = field(default_factory=list)

    def outlet_enthalpy(self, i: int, withdrawal: Withdrawal, fl: fluids.Fluid) -> float:
        s = fl.sat_T(float(self.T[i]))
        return s.h_v if withdrawal == "vapour" else s.h_l


def geometry(volume: float) -> tuple[float, float, float]:
    """Diameter, length and outer area of a horizontal cylinder with L/D = ASPECT."""
    d = (4.0 * volume / (math.pi * ASPECT)) ** (1.0 / 3.0)
    length = ASPECT * d
    return d, length, math.pi * d * length + math.pi * d**2 / 2.0


def simulate(inp: TankInput, n_out: int = 121) -> TankResult:
    fl = fluids.fluid(inp.fluid)
    comps = fluids.components(inp.fluid)
    names = tuple(comps)
    fractionates = len(names) > 1 and inp.withdrawal == "vapour"
    mix = fluids.blend(names) if len(names) > 1 else None

    _, _, area = geometry(inp.volume)
    ua = inp.U_amb * area
    m_dot = inp.mass_flow / 3600.0
    warnings: list[str] = []

    s0 = fl.sat_T(inp.T0)
    v_liq0 = (inp.fill_mass - inp.volume * s0.rho_v) / (s0.rho_l - s0.rho_v) * 1.0
    if v_liq0 > 0.9 * inp.volume:
        warnings.append(
            f"The liquid fills {v_liq0 / inp.volume:.0%} of the tank at {inp.T0 - 273.15:.0f} °C. "
            "Below 10 % vapour space the liquid can fill the tank completely when it warms up."
        )
    if v_liq0 <= 0:
        raise ValueError("the fill mass is too small to have any liquid in the tank")

    def liquid_mass(m: float, s: fluids.Saturation) -> float:
        return max((m - inp.volume * s.rho_v) / (1.0 - s.rho_v / s.rho_l), 0.0)

    def state(T: float, masses: np.ndarray):
        m = float(masses.sum())
        s = fl.sat_T(T)
        if mix is None:
            return s, s.p, {names[0]: 1.0}, s.h_fg, {names[0]: 1.0}
        liq = {n: float(mi / m) for n, mi in zip(names, masses)}
        try:
            b = mix.bubble(T, liq)
        except ValueError:
            return s, s.p, liq, s.h_fg, liq
        return s, b["p"], b["vapour"], b["h_fg"], liq

    def heater_power(T: float) -> float:
        if inp.heater == "off":
            return 0.0
        if inp.heater == "power":
            return inp.heater_power
        # thermostat: proportional band of 0.5 K
        return float(np.clip((inp.heater_T_set - T) / 0.5, 0.0, 1.0)) * inp.heater_power

    def rhs(_t: float, y: np.ndarray) -> np.ndarray:
        T, masses = y[0], y[1:]
        s, _, vap, h_fg, _ = state(T, masses)
        m = float(masses.sum())
        m_l = liquid_mass(m, s)
        if m_l <= 1e-3:
            return np.zeros_like(y)
        if inp.withdrawal == "vapour":
            dh = h_fg
            out = vap if fractionates else {n: comps[n] for n in names}
        else:
            dh = s.h_fg * s.rho_v / (s.rho_l - s.rho_v)
            liq = {n: float(mi / m) for n, mi in zip(names, masses)}
            out = liq
        heat_cap = m_l * s.cp_l + inp.wall_mass * STEEL_CP
        dT = (-m_dot * dh + ua * (inp.T_amb - T) + heater_power(T)) / heat_cap
        dm = np.array([-m_dot * out[n] for n in names])
        return np.concatenate(([dT], dm))

    def empty(_t, y):
        s = fl.sat_T(y[0])
        return liquid_mass(float(y[1:].sum()), s) - 0.02 * inp.fill_mass
    empty.terminal = True
    empty.direction = -1

    t_end = inp.duration * 3600.0
    y0 = np.concatenate(([inp.T0], [inp.fill_mass * comps[n] for n in names]))
    sol = solve_ivp(rhs, (0.0, t_end), y0, method="RK45", max_step=600.0, rtol=1e-6,
                    atol=np.concatenate(([1e-4], np.full(len(names), 1e-4))), events=empty, dense_output=True)
    t_stop = sol.t[-1]
    t = np.linspace(0.0, t_stop, n_out)
    Y = sol.sol(t)

    T_arr = Y[0]
    masses = Y[1:]
    p, liquid_frac, q_h, q_a, feed_c, liq_c = [], [], [], [], [], []
    for i in range(len(t)):
        s, p_i, vap, _, liq = state(T_arr[i], masses[:, i])
        m = float(masses[:, i].sum())
        m_l = liquid_mass(m, s)
        p.append(p_i)
        liquid_frac.append(m_l / s.rho_l / inp.volume)
        q_h.append(heater_power(T_arr[i]))
        q_a.append(ua * (inp.T_amb - T_arr[i]))
        feed_c.append(vap if fractionates else ({n: comps[n] for n in names} if inp.withdrawal == "vapour" else liq))
        liq_c.append(liq)
    p = np.array(p)

    t_low = None
    if inp.p_min is not None and np.any(p < inp.p_min):
        i = int(np.argmax(p < inp.p_min))
        t_low = float(t[i] / 3600.0)
    t_empty = float(t_stop / 3600.0) if sol.status == 1 else None

    return TankResult(
        t=t / 3600.0, T=T_arr, p=p, mass=masses.sum(axis=0), liquid_fraction=np.array(liquid_frac),
        q_heater=np.array(q_h), q_ambient=np.array(q_a), feed_composition=feed_c,
        liquid_composition=liq_c, t_pressure_low=t_low, t_empty=t_empty, warnings=warnings,
    )


def heater_to_hold(inp: TankInput) -> float:
    """Heater power [W] that keeps the tank at T0 against the withdrawal (steady state)."""
    fl = fluids.fluid(inp.fluid)
    s = fl.sat_T(inp.T0)
    m_dot = inp.mass_flow / 3600.0
    _, _, area = geometry(inp.volume)
    dh = s.h_fg if inp.withdrawal == "vapour" else s.h_fg * s.rho_v / (s.rho_l - s.rho_v)
    return max(m_dot * dh - inp.U_amb * area * (inp.T_amb - inp.T0), 0.0)
