"""
Every intermediate value in both modes side by side, with where each formula or
number comes from. [n] are the references of the thesis, the rest is literature
listed on the model page.

The user's tortuosity only applies to the mode they are in; the other column uses
the default of its own mode, so it always shows that mode as it is.
"""
from dataclasses import dataclass, replace

from . import pipeline


@dataclass(frozen=True)
class Row:
    group: str
    path: tuple[str, ...]          # where the value sits in pipeline.run() output
    symbol: str
    label: str
    unit: str
    thesis_source: str
    corrected_source: str          # "" = same as thesis


ROWS: tuple[Row, ...] = (
    Row("Equilibrium", ("equilibrium", "q"), "q", "adsorbed amount at 0.8 bar", "mol/kg",
        "literature isotherms, Tab. 2", ""),
    Row("Equilibrium", ("equilibrium", "c_star"), "c*", "gas density = equilibrium concentration", "kg/m³",
        "ideal gas, ch. 5", ""),
    Row("Equilibrium", ("equilibrium", "av"), "a_v", "adsorbed mass per bed volume", "kg/m³",
        "q ρ_n M, ch. 5", ""),
    Row("Equilibrium", ("equilibrium", "Ka"), "K_a", "Henry constant per bed volume", "–",
        "a_v / c*, Tab. 2", ""),
    Row("Equilibrium", ("equilibrium", "K_grain"), "K", "Henry constant in the Rosen groups", "–",
        "K_a taken as is", "K_a / (1 − ε) + ε_M, per grain volume (Rosen 1952)"),

    Row("Bed", ("hydraulics", "eps"), "ε", "voidage between the grains", "–",
        "(ρ_p − ρ_n) / ρ_p, ch. 4; counts the micropores too", "1 − ρ_n / (m_k / V_k), same ch. 4 data"),
    Row("Bed", ("hydraulics", "z"), "z", "ε / (1 − ε)", "–", "ch. 4", ""),
    Row("Bed", ("hydraulics", "w_k"), "w_k", "velocity in the empty column", "m/s", "V̇ / A, Tab. 6", ""),
    Row("Bed", ("hydraulics", "w"), "w", "velocity between the grains", "m/s", "w_k / ε, Tab. 6", ""),

    Row("Diffusion", ("diffusion", "D"), "D", "molecular (self-)diffusion", "m²/s",
        "kinetic theory, hard spheres [9], Tab. 8", "Chapman–Enskog ρD/μ = 1.32 with the gas viscosity [9]"),
    Row("Diffusion", ("diffusion", "DK"), "D_K", "Knudsen diffusion", "m²/s",
        "[10] in the zeolite window, Å converted with 1e-8", "[10] in the binder macropores, 0.59 µm (Hu et al. 2014)"),
    Row("Diffusion", ("diffusion", "tau"), "τ", "tortuosity factor", "–",
        "not included (ch. 5.2)", "macropores, Hu et al. 2014; see also [8]"),
    Row("Diffusion", ("diffusion", "D_pore"), "D_p", "diffusion in the macropores", "m²/s",
        "–", "Bosanquet 1/D + 1/D_K, over τ [11]"),
    Row("Diffusion", ("rosen", "K_D"), "K D'", "transport into the grain", "m²/s",
        "K_a D'", "ε_M D_p (macropore control, Ruthven 1984)"),
    Row("Diffusion", ("diffusion", "D_eff"), "D'", "diffusion in the grain (Rosen)", "m²/s",
        "1/D + 1/D_K [11], Tab. 9", "ε_M D_p / K"),
    Row("Diffusion", ("dispersion", "D_ax"), "D_ax", "axial dispersion", "m²/s",
        "not in the thesis (app only)", "Edwards & Richardson 1968"),

    Row("Film", ("film", "Re"), "Re", "Reynolds", "–", "w d_z ρ / μ", "w_k d_p ρ / μ"),
    Row("Film", ("film", "Sc"), "Sc", "Schmidt", "–", "μ / (ρ D)", ""),
    Row("Film", ("film", "Sh"), "Sh", "Sherwood", "–",
        "0.395 Re^0.54 Sc^0.33, Paderewski [3]", "2 + 1.1 Sc^1/3 Re^0.6, Wakao & Funazkri 1978"),
    Row("Film", ("film", "kcg"), "k_c,g", "film mass transfer coefficient", "m/s",
        "Sh D / d_z, Tab. 7", "Sh D / d_p"),

    Row("Column", ("rosen", "lambda"), "λ'", "Rosen length parameter", "–", "3 D' K H / (z w R²), Tab. 10", ""),
    Row("Column", ("rosen", "psi"), "ψ", "Rosen film / grain resistance", "–", "D' K / (R k_c,g), Tab. 11", ""),
    Row("Column", ("dispersion", "k_ldf"), "k_LDF", "LDF coefficient", "1/s",
        "15 D' / (R² (1 + 5ψ)), Glueckauf 1955 (app only)", ""),
    Row("Column", ("spreading", "sigma_rel"), "σ/t", "width of the front", "–",
        "moments of the LDF model (app only)", ""),
    Row("Column", ("t_stoich",), "t_s", "stoichiometric time (c/c₀ = 0.5)", "s", "Rosen, τ' = 2/3 λ'", ""),
    Row("Column", ("t_breakthrough",), "t_b", "breakthrough time", "s", "Rosen, Tab. 13-14", ""),
)


def _get(res: dict, path: tuple[str, ...], threshold: float) -> float | None:
    if path == ("t_breakthrough",):
        return res["breakthrough"][f"{threshold:g}"]
    if path == ("rosen", "K_D"):
        bed = res["bed"]
        return bed.ka * bed.d_eff
    node = res
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return float(node)


def rows(inp: pipeline.BedInput, threshold: float) -> list[dict]:
    """Both modes for one input. Raises pipeline.NoAdsorptionData like pipeline.run."""
    out = {}
    for mode in ("thesis", "corrected"):
        tau = inp.tortuosity if inp.mode == mode else None
        out[mode] = pipeline.run(replace(inp, mode=mode, tortuosity=tau, thresholds=(threshold,)))
    return [
        {
            "group": r.group,
            "symbol": r.symbol,
            "label": r.label,
            "unit": r.unit,
            "thesis": _get(out["thesis"], r.path, threshold),
            "corrected": _get(out["corrected"], r.path, threshold),
            "thesis_source": r.thesis_source,
            "corrected_source": r.corrected_source or r.thesis_source,
        }
        for r in ROWS
    ]
