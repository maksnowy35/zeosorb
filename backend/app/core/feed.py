"""
Feed analysis: storage tank -> reducer -> pipe segments -> adsorber inlet, over a whole campaign.

Puts tank.py, feedline.py and the isotherms together and answers the operator's questions:
what arrives at the adsorber (temperature, superheat, viscosity, flow), how much heat each segment
has to put in or take out, whether that stays the same while the tank empties, and how the
choice of feed temperature trades off against the bed's capacity.
"""
from dataclasses import dataclass

import numpy as np

from . import feedline, fluids, isotherms, materials, tank

C0 = 273.15
REDUCER_MARGIN = 1.0e5       # Pa, the reducer needs this much above its outlet to regulate


@dataclass
class FeedSetup:
    fluid: str
    mass_flow: float              # kg/h
    reducer: float                # Pa abs
    tank: tank.TankInput
    segments: list[feedline.Segment]
    target: float                 # K
    superheat_min: float          # K
    zeolite: str


def dew_point(fluid_key: str, p: float, composition: dict[str, float]) -> float:
    """Dew temperature of the actual composition (true mixture for blends)."""
    names = tuple(composition)
    if len(names) == 1:
        return fluids.fluid(fluid_key).T_dew(p)
    try:
        return fluids.blend(names).dew_temperature(p, composition)
    except ValueError:
        return fluids.fluid(fluid_key).T_dew(p)


def tank_outlet(setup: FeedSetup, T_tank: float) -> tuple[float, float]:
    """(pressure, enthalpy) of what leaves the tank, consistent with the pseudo-pure properties used in
    the line. For blends the real tank pressure (bubble point of the mixture) is checked separately."""
    fl = fluids.fluid(setup.fluid)
    s = fl.sat_T(T_tank)
    if setup.tank.withdrawal == "vapour":
        return s.p, s.h_v
    return fl.p_bubble(T_tank), s.h_l


def _r(v, n=4):
    return float(f"{v:.{n}g}") if v is not None and np.isfinite(v) else None


def analyse(setup: FeedSetup, n_campaign: int = 9) -> dict:
    fl = fluids.fluid(setup.fluid)
    setup.tank.mass_flow = setup.mass_flow
    setup.tank.p_min = setup.reducer + REDUCER_MARGIN
    tk = tank.simulate(setup.tank)
    comp0 = tk.feed_composition[0]

    line = feedline.simulate(setup.fluid, setup.mass_flow, *tank_outlet(setup, float(tk.T[0])),
                             setup.reducer, setup.segments)
    line.reducer["p_in"] = float(tk.p[0])
    out = line.outlet
    dew_out = dew_point(setup.fluid, out.p, comp0)
    superheat_out = out.T - dew_out if out.phase != "two-phase" else 0.0

    # campaign: the same line settings while the tank empties and cools
    idx = np.unique(np.linspace(0, len(tk.t) - 1, n_campaign).round().astype(int))
    camp = {"t_h": [], "outlet_C": [], "superheat_K": [], "p_tank_bar": [], "T_tank_C": [], "duty_W": [], "feed_ok": []}
    for i in idx:
        p_t = float(tk.p[i])
        ok = p_t >= setup.reducer + REDUCER_MARGIN
        r = feedline.simulate(setup.fluid, setup.mass_flow, *tank_outlet(setup, float(tk.T[i])),
                              setup.reducer, setup.segments)
        d = dew_point(setup.fluid, r.outlet.p, tk.feed_composition[i])
        camp["t_h"].append(_r(tk.t[i]))
        camp["outlet_C"].append(_r(r.outlet.T - C0))
        camp["superheat_K"].append(_r(r.outlet.T - d if r.outlet.phase != "two-phase" else 0.0))
        camp["p_tank_bar"].append(_r(p_t / 1e5))
        camp["T_tank_C"].append(_r(tk.T[i] - C0))
        camp["duty_W"].append(_r(sum(s.duty for s in r.segments)))
        camp["feed_ok"].append(bool(ok))

    # capacity of the bed against feed temperature, at the reducer pressure
    capacity = None
    names = list(comp0)
    has_data = all(materials.adsorbed_amount(setup.zeolite, n) is not None for n in names)
    t_low = dew_point(setup.fluid, setup.reducer, comp0)
    if has_data:
        temps = np.linspace(max(t_low + 1.0, 233.15), 523.15, 45)
        cap = isotherms.capacity_curve(setup.zeolite, comp0, setup.reducer, temps)
        t_vap = fl.T_dew(setup.reducer) + 0.5     # the pseudo-pure blend has its own dew line
        mu = [fl.pt(setup.reducer, max(float(T), t_vap)).mu for T in temps]
        capacity = {
            "T_C": [_r(T - C0) for T in temps],
            "q_kg": {n: [_r(v) for v in cap["q_kg"][:, i]] for i, n in enumerate(cap["names"])},
            "total_kg": [_r(v) for v in cap["q_kg"].sum(axis=1)],
            "mu_uPa_s": [_r(m * 1e6) for m in mu],
            "dew_C": _r(t_low - C0),
            "min_safe_C": _r(t_low + setup.superheat_min - C0),
        }

    hold = tank.heater_to_hold(setup.tank)
    res = {
        "fluid": setup.fluid,
        "composition": comp0,
        "reducer": {
            "p_in_bar": _r(line.reducer["p_in"] / 1e5), "p_out_bar": _r(line.reducer["p_out"] / 1e5),
            "T_in_C": _r(line.reducer["T_in"] - C0), "T_out_C": _r(line.reducer["T_out"] - C0),
            "x_out": _r(line.reducer["x_out"]) if line.reducer["x_out"] is not None else None,
            "phase_out": line.reducer["phase_out"],
        },
        "line": {
            "z": [_r(v) for v in line.z], "T_C": [_r(v - C0) for v in line.T], "T_dew_C": [_r(v - C0) for v in line.T_dew],
            "p_bar": [_r(v / 1e5, 6) for v in line.p], "x": [None if np.isnan(v) else _r(v) for v in line.x],
            "rho": [_r(v) for v in line.rho], "mu_uPa_s": [_r(v * 1e6) for v in line.mu], "u": [_r(v) for v in line.u],
            "re": [_r(v) for v in line.re], "h_in": [_r(v) for v in line.h_in], "q_W_m": [_r(v) for v in line.q_lin],
            "T_wall_C": [_r(v - C0) for v in line.T_wall], "T_outside_C": [_r(v - C0) for v in line.T_outside],
        },
        "segments": [{
            "name": s.name, "z_start": s.z_start, "z_end": s.z_end, "T_in_C": _r(s.T_in - C0), "T_out_C": _r(s.T_out - C0),
            "x_in": _r(s.x_in) if s.x_in is not None else None, "x_out": _r(s.x_out) if s.x_out is not None else None,
            "duty_W": _r(s.duty), "dp_Pa": _r(s.dp), "residence_s": _r(s.residence), "h_mean": _r(s.h_mean),
            "ntu": _r(s.ntu) if s.ntu is not None else None, "re_in": _r(s.re_in), "re_out": _r(s.re_out),
            "u_in": _r(s.velocity_in), "u_out": _r(s.velocity_out),
            "wall_min_C": _r(s.wall_T_min - C0), "wall_max_C": _r(s.wall_T_max - C0),
        } for s in line.segments],
        "outlet": {
            "T_C": _r(out.T - C0), "p_bar": _r(out.p / 1e5, 6), "phase": out.phase, "x": _r(out.x) if out.x is not None else None,
            "dew_C": _r(dew_out - C0), "superheat_K": _r(superheat_out), "mu_uPa_s": _r(out.mu * 1e6),
            "rho": _r(out.rho), "volume_flow_m3h": _r(setup.mass_flow / out.rho),
        },
        "tank": {
            "t_h": [_r(v) for v in tk.t], "T_C": [_r(v - C0) for v in tk.T], "p_bar": [_r(v / 1e5) for v in tk.p],
            "mass_kg": [_r(v) for v in tk.mass], "liquid_fraction": [_r(v) for v in tk.liquid_fraction],
            "q_heater_W": [_r(v) for v in tk.q_heater], "q_ambient_W": [_r(v) for v in tk.q_ambient],
            "feed_composition": {n: [_r(c.get(n, 0.0)) for c in tk.feed_composition] for n in names},
            "t_pressure_low": tk.t_pressure_low, "t_empty": tk.t_empty, "hold_power_W": _r(hold),
            "p_needed_bar": _r((setup.reducer + REDUCER_MARGIN) / 1e5),
        },
        "campaign": camp,
        "capacity": capacity,
        "target_C": _r(setup.target - C0),
        "superheat_min_K": setup.superheat_min,
        "warnings": line.warnings + tk.warnings,
    }
    res["findings"] = findings(setup, res, line, tk)
    return res


def findings(setup: FeedSetup, res: dict, line: feedline.LineResult, tk: tank.TankResult) -> list[dict]:
    out: list[dict] = []
    add = lambda sev, text: out.append({"severity": sev, "text": text})
    o, red, segs = res["outlet"], res["reducer"], res["segments"]

    for w in res["warnings"]:
        add("warning", w)

    if red["phase_out"] == "two-phase":
        evap = next((s for s in segs if s["x_out"] is None), None)
        where = f"{evap['name']} finishes evaporating it" if evap else "no segment finishes evaporating it"
        add("info" if evap else "warning",
            f"The reducer turns the {setup.tank.withdrawal} into a two-phase mixture at {red['T_out_C']:.0f} °C "
            f"(vapour quality {red['x_out']:.2f}); {where}. Evaporation takes most of the heat: "
            f"{sum(s['duty_W'] for s in segs if s['x_in'] is not None) / 1000:.2f} kW.")
    else:
        add("info", f"Across the reducer ({red['p_in_bar']:.1f} -> {red['p_out_bar']:.2f} bar) the gas cools from "
                    f"{red['T_in_C']:.0f} °C to {red['T_out_C']:.0f} °C (Joule-Thomson).")

    if o["phase"] != "vapour":
        add("warning", f"Liquid reaches the adsorber (vapour quality {o['x']}). Droplets on hot zeolite crack the "
                       "pellets and the feed is no longer what the model assumes; add heat upstream.")
    elif o["superheat_K"] < setup.superheat_min:
        add("warning", f"The gas arrives only {o['superheat_K']:.1f} K above its dew point ({o['dew_C']:.0f} °C); "
                       f"the margin asked for is {setup.superheat_min:.0f} K.")

    target = res["target_C"]
    gap = o["T_C"] - target
    if abs(gap) > 2.0:
        last = segs[-1]
        text = (f"The gas reaches the adsorber at {o['T_C']:.0f} °C, {abs(gap):.0f} K {'below' if gap < 0 else 'above'} "
                f"the {target:.0f} °C wanted.")
        if gap < 0 and last["ntu"] is not None and last["ntu"] < 0.7:
            text += (f" {last['name']} (D {1000 * setup.segments[-1].D:.0f} mm) adds only "
                     f"{last['T_out_C'] - last['T_in_C']:.0f} K: at {last['u_out']:.2f} m/s the inside coefficient is "
                     f"{last['h_mean']:.0f} W/m²K (NTU {last['ntu']:.2f}), so the wide pipe works as a buffer more than as a heater.")
        text += " 'Find setting' searches the jacket temperature or trace power that hits the target."
        add("warning" if gap < 0 else "info", text)
    else:
        add("info", f"The gas reaches the adsorber at {o['T_C']:.0f} °C, within 2 K of the {target:.0f} °C wanted.")

    # tank and campaign
    t = res["tank"]
    camp = res["campaign"]
    if setup.tank.withdrawal == "vapour" and setup.tank.heater == "off":
        add("warning" if tk.t_pressure_low else "info",
            f"Drawing vapour cools the tank from {t['T_C'][0]:.0f} °C to {t['T_C'][-1]:.0f} °C in {t['t_h'][-1]:.0f} h "
            f"(pressure {t['p_bar'][0]:.1f} -> {t['p_bar'][-1]:.1f} bar). "
            + (f"After {tk.t_pressure_low:.1f} h it is below the {t['p_needed_bar']:.1f} bar the reducer needs. "
               if tk.t_pressure_low else "")
            + f"About {t['hold_power_W'] / 1000:.1f} kW on the tank (heating blanket or water bath) holds it at "
              f"{setup.tank.T0 - C0:.0f} °C.")
    elif tk.t_pressure_low:
        add("warning", f"After {tk.t_pressure_low:.1f} h the tank pressure falls below the {t['p_needed_bar']:.1f} bar the reducer needs.")
    if tk.t_empty:
        add("warning", f"The liquid runs out after {tk.t_empty:.1f} h.")

    spread = max(camp["outlet_C"]) - min(camp["outlet_C"])
    if spread > 2.0:
        add("warning" if spread > 5.0 else "info", f"With fixed jacket temperatures the gas at the adsorber drifts between {min(camp['outlet_C']):.0f} °C "
                       f"and {max(camp['outlet_C']):.0f} °C over the campaign, because the tank state changes. A temperature "
                       f"controller on the first jacket (or a heated tank) keeps it steady.")
    else:
        add("info", f"Over {camp['t_h'][-1]:.0f} h the gas at the adsorber stays within {spread:.1f} K.")

    names = list(res["composition"])
    if len(names) > 1:
        fc = t["feed_composition"]
        lead = max(names, key=lambda n: abs(fc[n][-1] - fc[n][0]) + abs(fc[n][0] - fluids.components(setup.fluid)[n]))
        nominal = fluids.components(setup.fluid)[lead]
        shift = max(abs(fc[lead][0] - nominal), abs(fc[lead][-1] - nominal))
        if setup.tank.withdrawal == "vapour" and shift > 0.02:
            add("warning" if shift > 0.05 else "info", f"Vapour drawn off {setup.fluid} is not {setup.fluid}: it carries {fc[lead][0]:.0%} {lead} at the start and "
                           f"{fc[lead][-1]:.0%} after {t['t_h'][-1]:.0f} h (nominal {nominal:.0%}). Drawing liquid and evaporating it "
                           f"in the line keeps the feed at the blend's composition.")

    cap = res["capacity"]
    if cap:
        T = np.array(cap["T_C"], dtype=float)
        tot = np.array(cap["total_kg"], dtype=float)
        mu = np.array(cap["mu_uPa_s"], dtype=float)
        lo = cap["min_safe_C"]
        q_lo = float(np.interp(lo, T, tot))
        q_t = float(np.interp(target, T, tot))
        mu_lo = float(np.interp(lo, T, mu))
        mu_t = float(np.interp(target, T, mu))
        add("info",
            f"Viscosity is not a lever on its own: it follows the temperature, from {mu_lo:.1f} µPa·s at {lo:.0f} °C "
            f"(dew point + margin) to {mu_t:.1f} µPa·s at {target:.0f} °C, and changes the bed's Reynolds number and pressure "
            f"drop only by that ratio. Temperature matters through capacity: {setup.zeolite} holds {q_lo:.3f} kg/kg at "
            f"{lo:.0f} °C and {q_t:.3f} kg/kg at {target:.0f} °C, if the bed runs at the feed temperature.")
    return out
