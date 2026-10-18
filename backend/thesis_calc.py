"""
Calculations from my engineering thesis:

    "Analiza procesu adsorpcji czynnikow chlodniczych na wybranych zlozach sorpcyjnych"
    Politechnika Warszawska, MEiL, Zaklad Chlodnictwa i Energetyki Budynku

Rewritten from the Excel sheets into Python so I can play with the parameters
without copying formulas between cells. Same constants and assumptions as in
chapters 5 and 6 of the thesis:

  * T = 100 C, averaged process pressure p = 0.8 bar
  * single component, Henry constant from one isotherm point (0.8 bar)
  * Rosen solution for the breakthrough curve (erf approximation)
"""
import math

# --- constants --------------------------------------------------------------
R_UNIV = 8315.0      # J/(kmol*K)
K_B = 1.38e-23       # J/K
N_A = 6.022e23       # 1/mol

T = 373.0            # K
P = 0.8e5            # Pa
H = 2.89             # m  - bed height
A = 0.196            # m2 - column cross section

# --- refrigerants (Tab. 1) ---------------------------------------------------
# M [kg/kmol], d - molecule size from Avogadro [A], mu - CoolProp at 100 C, 0.8 bar [Pa*s]
REFRIGERANTS = {
    "R32":   {"formula": "CH2F2",   "M": 52.02,  "d": 3.34, "mu": 1.67e-5},
    "R22":   {"formula": "CHClF2",  "M": 86.47,  "d": 4.14, "mu": 1.72e-5},
    "R134a": {"formula": "CF3CH2F", "M": 102.03, "d": 4.68, "mu": 1.47e-5},
    "R143a": {"formula": "C2H3F3",  "M": 84.04,  "d": 4.40, "mu": 1.38e-5},
    "R125":  {"formula": "C2HF5",   "M": 120.02, "d": 4.68, "mu": 1.60e-5},
    "R152a": {"formula": "C2H4F2",  "M": 66.05,  "d": 4.40, "mu": 1.39e-5},
}

# --- zeolites (chapter 4 + Tab. 4) ---------------------------------------------
# R - grain radius [m], d_pore [A], eps - bed porosity, rho_bulk [kg/m3], dz - equivalent channel diameter [m]
ZEOLITES = {
    "4A":  {"R": 0.002,   "d_pore": 4.0, "eps": 0.633, "rho_bulk": 827.9,  "dz": 2.53e-8},
    "5A":  {"R": 0.0025,  "d_pore": 5.0, "eps": 0.72,  "rho_bulk": 650.0,  "dz": 3.61e-8},
    "13X": {"R": 0.00375, "d_pore": 9.0, "eps": 0.45,  "rho_bulk": 1071.2, "dz": 4.09e-8},
}

# adsorbed amount at 0.8 bar [mol/kg] read from literature isotherms (Tab. 2)
# missing pairs = no data found in literature
ADSORPTION = {
    "4A":  {"R32": 4.8, "R22": 1.65, "R125": 2.65},
    "5A":  {"R32": 4.8, "R22": 1.95, "R134a": 2.25, "R143a": 1.5, "R125": 1.95, "R152a": 2.4},
    "13X": {"R32": 4.6, "R134a": 2.3, "R143a": 1.5, "R125": 1.8, "R152a": 3.0},
}

# Sherwood correlation Sh = C * Re^A * Sc^B  (Tab. 3, "ziarna", Re < 30)
SH_C, SH_A, SH_B = 0.395, 0.54, 0.33

# Tab. 12 - E vs c/c0
E_TABLE = [
    (0.024, -1.40),
    (0.045, -1.20),
    (0.079, -1.00),
    (0.240, -0.50),
    (0.500, 0.00),
    (0.715, 0.40),
    (0.920, 1.00),
]


def c_star(M, p=P, t=T):
    """Equilibrium concentration (= gas density) [kg/m3]."""
    return p * M / (R_UNIV * t)


def henry_constant(q, rho_bulk, M, p=P):
    """Ka = av / c*, av = q * rho_bulk * M  [kg/m3]."""
    av = q * rho_bulk * M / 1000.0
    return av / c_star(M, p), av


def d_molecular(d_angstrom, M, p=P, t=T):
    """Gas diffusion coefficient from kinetic theory [m2/s]."""
    m = M / 1000.0 / N_A
    d = d_angstrom * 1e-10
    return 2.0 / 3.0 * math.sqrt(K_B * t / (math.pi * m)) * K_B * t / (math.pi * d ** 2 * p)


def d_knudsen(d_pore_angstrom, M, t=T):
    """Knudsen diffusion coefficient [m2/s]."""
    dp = d_pore_angstrom * 1e-8  # A -> m
    return dp / 3.0 * math.sqrt(8 * R_UNIV * t / (math.pi * M))


def d_effective(D, DK):
    """1/D' = 1/D + 1/DK"""
    return 1.0 / (1.0 / D + 1.0 / DK)


def lookup_E(threshold):
    """Linear interpolation in Tab. 12."""
    if threshold <= E_TABLE[0][0]:
        return E_TABLE[0][1]
    for (x0, e0), (x1, e1) in zip(E_TABLE, E_TABLE[1:]):
        if x0 <= threshold <= x1:
            return e0 + (e1 - e0) * (threshold - x0) / (x1 - x0)
    return E_TABLE[-1][1]


def calculate(refrigerant, zeolite, mass_flow=30.0, threshold=0.05):
    ref = REFRIGERANTS[refrigerant]
    zeo = ZEOLITES[zeolite]
    q = ADSORPTION[zeolite].get(refrigerant)
    if q is None:
        raise ValueError(f"no adsorption data for {refrigerant} on {zeolite}")

    M, mu = ref["M"], ref["mu"]
    eps, R, dz = zeo["eps"], zeo["R"], zeo["dz"]

    # equilibrium
    rho = c_star(M)
    Ka, av = henry_constant(q, zeo["rho_bulk"], M)

    # diffusion
    D = d_molecular(ref["d"], M)
    DK = d_knudsen(zeo["d_pore"], M)
    Dp = d_effective(D, DK)

    # velocities
    V = mass_flow / rho / 3600.0     # m3/s
    wk = V / A                       # m/s - in empty column
    w = wk / eps                     # m/s - in bed channels

    # film mass transfer
    Re = w * dz * rho / mu
    Sc = mu / (D * rho)
    Sh = SH_C * Re ** SH_A * Sc ** SH_B
    kcg = Sh * D / dz

    # Rosen parameters
    z = eps / (1 - eps)
    lam = 3 * Dp * Ka * H / (z * w * R ** 2)
    psi = Dp * Ka / (R * kcg)

    # breakthrough time
    E = lookup_E(threshold)
    spread = math.sqrt((1 + 5 * psi) / (5 * lam))
    tau = R ** 2 * lam / (2 * Dp) * (2.0 / 3.0) * (1 + 2 * E * spread) + H / w

    return {
        "refrigerant": refrigerant,
        "zeolite": zeolite,
        "mass_flow": mass_flow,
        "threshold": threshold,
        "c_star": rho,
        "q": q,
        "av": av,
        "Ka": Ka,
        "D": D,
        "DK": DK,
        "D_eff": Dp,
        "V": V,
        "wk": wk,
        "w": w,
        "Re": Re,
        "Sc": Sc,
        "Sh": Sh,
        "kcg": kcg,
        "z": z,
        "lambda": lam,
        "psi": psi,
        "E": E,
        "tau_s": tau,
        "tau_h": tau / 3600.0,
    }


if __name__ == "__main__":
    # quick check vs thesis (R22 on 4A, m1 = 30 kg/h)
    for thr in (0.05, 0.024):
        r = calculate("R22", "4A", 30, thr)
        print(f"c/c0={thr}: Ka={r['Ka']:.2f} D'={r['D_eff']:.2e} lambda={r['lambda']:.0f} "
              f"psi={r['psi']:.3f} tau={r['tau_s']:.0f} s ({r['tau_h']:.2f} h)")
