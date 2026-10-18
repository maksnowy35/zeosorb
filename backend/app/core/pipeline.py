"""Whole calculation chain for one refrigerant / zeolite pair."""
import math
from dataclasses import dataclass, field

from . import materials, rosen, transport
from .constants import BED_HEIGHT, COLUMN_DIAMETER, P_PROCESS, T_PROCESS


class NoAdsorptionData(ValueError):
    pass


@dataclass
class BedInput:
    refrigerant: str
    zeolite: str
    mass_flow: float = 30.0                # kg/h
    bed_height: float = BED_HEIGHT         # m
    column_diameter: float = COLUMN_DIAMETER
    pressure: float = P_PROCESS            # Pa
    temperature: float = T_PROCESS         # K
    thresholds: tuple[float, ...] = field(default=(0.024, 0.05))


def run(inp: BedInput) -> dict:
    ref = materials.refrigerants()[inp.refrigerant]
    zeo = materials.zeolites()[inp.zeolite]
    q = materials.adsorbed_amount(inp.zeolite, inp.refrigerant)
    if q is None:
        raise NoAdsorptionData(f"no adsorption data for {inp.refrigerant} on {inp.zeolite}")

    M, mu = ref.molar_mass, ref.viscosity
    eps, R, dz = zeo.bed_porosity, zeo.grain_radius, zeo.channel_diameter

    # equilibrium
    rho = transport.gas_density(M, inp.pressure, inp.temperature)
    ka, av = transport.henry_constant(q, zeo.bulk_density, M, rho)

    # diffusion
    d_mol = transport.molecular_diffusivity(ref.molecule_size, M, inp.pressure, inp.temperature)
    d_kn = transport.knudsen_diffusivity(zeo.pore_diameter, M, inp.temperature)
    d_eff = transport.effective_diffusivity(d_mol, d_kn)

    # hydraulics
    area = math.pi * inp.column_diameter**2 / 4.0
    v_dot = inp.mass_flow / rho / 3600.0
    w_k = v_dot / area
    w = w_k / eps
    z = eps / (1.0 - eps)

    # film
    re = transport.reynolds(w, dz, rho, mu)
    sc = transport.schmidt(mu, d_mol, rho)
    sh = transport.sherwood(re, sc)
    kcg = transport.film_coefficient(sh, d_mol, dz)

    # Rosen
    lam, psi = rosen.parameters(d_eff, ka, inp.bed_height, z, w, R, kcg)
    t_stoich = rosen.stoichiometric_time(lam, d_eff, R, inp.bed_height, w)
    times = {
        f"{thr:g}": rosen.breakthrough_time(thr, lam, psi, d_eff, R, inp.bed_height, w)
        for thr in inp.thresholds
    }

    return {
        "equilibrium": {"q": q, "c_star": rho, "av": av, "Ka": ka},
        "diffusion": {"D": d_mol, "DK": d_kn, "D_eff": d_eff},
        "hydraulics": {"area": area, "V": v_dot, "w_k": w_k, "w": w, "z": z},
        "film": {"Re": re, "Sc": sc, "Sh": sh, "kcg": kcg},
        "rosen": {"lambda": lam, "psi": psi, "spread": rosen.spread(lam, psi)},
        "t_stoich": t_stoich,
        "breakthrough": times,
        "_curve_args": (lam, psi, d_eff, R, inp.bed_height, w),
    }
