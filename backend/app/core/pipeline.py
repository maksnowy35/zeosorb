"""Whole calculation chain for one refrigerant / zeolite pair."""
import math
from dataclasses import dataclass, field
from typing import Literal

from . import materials, rosen, transport
from .constants import BED_HEIGHT, COLUMN_DIAMETER, P_PROCESS, T_PROCESS

Mode = Literal["corrected", "thesis"]


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
    mode: Mode = "corrected"
    tortuosity: float = 1.0


@dataclass
class Bed:
    """Everything the column models need, in SI units."""
    height: float        # m
    w: float             # interstitial velocity, m/s
    z: float             # eps / (1 - eps)
    radius: float        # grain radius, m
    ka: float            # Henry constant, -
    d_eff: float         # D', m2/s
    kcg: float           # film coefficient, m/s
    d_ax: float          # axial dispersion, m2/s
    lam: float           # Rosen lambda'
    psi: float           # Rosen psi

    @property
    def t_ref(self) -> float:
        """Gas residence time H / w."""
        return self.height / self.w

    @property
    def kappa(self) -> float:
        """Capacity ratio Ka / z."""
        return self.ka / self.z

    @property
    def peclet(self) -> float:
        return self.w * self.height / self.d_ax

    @property
    def k_ldf(self) -> float:
        """Glueckauf LDF coefficient with film resistance in series: 15 D' / (R^2 (1 + 5 psi))."""
        return 15.0 * self.d_eff / (self.radius**2 * (1.0 + 5.0 * self.psi))

    def spreading(self) -> dict[str, float]:
        """Relative variance of the breakthrough front (sigma_t / t_stoich)^2 from the moments of the LDF model."""
        kap = self.kappa
        mt = 2.0 * kap / (self.k_ldf * self.t_ref * (1.0 + kap) ** 2)
        ax = 2.0 / self.peclet
        total = mt + ax
        return {
            "mass_transfer": mt,
            "axial_dispersion": ax,
            "total": total,
            "sigma_rel": math.sqrt(total),
            "mass_transfer_share": mt / total,
        }


def run(inp: BedInput) -> dict:
    ref = materials.refrigerants()[inp.refrigerant]
    zeo = materials.zeolites()[inp.zeolite]
    q = materials.adsorbed_amount(inp.zeolite, inp.refrigerant)
    if q is None:
        raise NoAdsorptionData(f"no adsorption data for {inp.refrigerant} on {inp.zeolite}")

    thesis = inp.mode == "thesis"
    M, mu = ref.molar_mass, ref.viscosity
    eps, R, dz = zeo.bed_porosity, zeo.grain_radius, zeo.channel_diameter
    d_p = 2.0 * R

    # equilibrium
    rho = transport.gas_density(M, inp.pressure, inp.temperature)
    ka, av = transport.henry_constant(q, zeo.bulk_density, M, rho)

    # diffusion
    d_mol = transport.molecular_diffusivity(ref.molecule_size, M, inp.pressure, inp.temperature)
    pore_scale = transport.THESIS_PORE_SCALE if thesis else transport.ANGSTROM
    d_kn = transport.knudsen_diffusivity(zeo.pore_diameter, M, inp.temperature, scale=pore_scale)
    d_eff = transport.effective_diffusivity(d_mol, d_kn, inp.tortuosity)

    # hydraulics
    area = math.pi * inp.column_diameter**2 / 4.0
    v_dot = inp.mass_flow / rho / 3600.0
    w_k = v_dot / area
    w = w_k / eps
    z = eps / (1.0 - eps)

    # film
    sc = transport.schmidt(mu, d_mol, rho)
    if thesis:
        re = transport.reynolds(w, dz, rho, mu)
        sh = transport.sherwood(re, sc)
        kcg = transport.film_coefficient(sh, d_mol, dz)
        correlation = "thesis: Sh = 0.395 Re^0.54 Sc^0.33, L = dz"
    else:
        re = transport.reynolds(w_k, d_p, rho, mu)
        sh = transport.sherwood_wakao_funazkri(re, sc)
        kcg = transport.film_coefficient(sh, d_mol, d_p)
        correlation = "Wakao-Funazkri: Sh = 2 + 1.1 Sc^1/3 Re_p^0.6, L = d_p"

    # dispersion (not in the thesis - only used by the LDF model and the spreading budget)
    d_ax = transport.axial_dispersion(d_mol, w, d_p)

    # Rosen
    lam, psi = rosen.parameters(d_eff, ka, inp.bed_height, z, w, R, kcg)
    bed = Bed(height=inp.bed_height, w=w, z=z, radius=R, ka=ka, d_eff=d_eff,
              kcg=kcg, d_ax=d_ax, lam=lam, psi=psi)
    t_stoich = rosen.stoichiometric_time(lam, d_eff, R, inp.bed_height, w)
    times = {
        f"{thr:g}": rosen.breakthrough_time(thr, lam, psi, d_eff, R, inp.bed_height, w)
        for thr in inp.thresholds
    }

    return {
        "equilibrium": {"q": q, "c_star": rho, "av": av, "Ka": ka},
        "diffusion": {"D": d_mol, "DK": d_kn, "D_eff": d_eff},
        "hydraulics": {"area": area, "V": v_dot, "w_k": w_k, "w": w, "z": z, "t_residence": bed.t_ref},
        "film": {"Re": re, "Sc": sc, "Sh": sh, "kcg": kcg},
        "film_correlation": correlation,
        "rosen": {"lambda": lam, "psi": psi, "spread": rosen.spread(lam, psi)},
        "dispersion": {"D_ax": d_ax, "Pe": bed.peclet, "k_ldf": bed.k_ldf},
        "spreading": bed.spreading(),
        "t_stoich": t_stoich,
        "breakthrough": times,
        "bed": bed,
    }
