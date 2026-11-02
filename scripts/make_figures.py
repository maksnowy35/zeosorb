"""
Figures for the README (docs/img). Uses the backend package directly, no API needed.

    pip install -r backend/requirements.txt matplotlib pillow
    python scripts/make_figures.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import ldf, pipeline, rosen  # noqa: E402

OUT = ROOT / "docs" / "img"
PAPER, INK, STEEL, FROST, OCHRE, SIGNAL = "#eef1ef", "#1d2a33", "#5b6b76", "#1a78bd", "#c8a24a", "#b4452f"

plt.rcParams.update({
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "axes.edgecolor": STEEL,
    "axes.labelcolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": INK,
    "grid.alpha": 0.07,
    "xtick.color": STEEL,
    "ytick.color": STEEL,
    "font.size": 10,
    "legend.frameon": False,
})


def run(mode: str, ref: str = "R22", zeo: str = "4A"):
    res = pipeline.run(pipeline.BedInput(ref, zeo, mode=mode, thresholds=(0.05,)))
    b = res["bed"]
    t_end = 1.6 * res["t_stoich"]
    t, c = rosen.curve(b.lam, b.psi, b.d_eff, b.radius, b.height, b.w, n=600, t_max=t_end)
    return res, t, c, ldf.simulate(b, t_end=t_end, n_profiles=60)


def breakthrough_modes() -> None:
    thesis, t_th, c_th, _ = run("thesis")
    corr, t_co, c_co, sol = run("corrected")

    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=150)
    # thesis front comes much earlier - draw it over the same time span as the corrected one
    b = thesis["bed"]
    t_th, c_th = rosen.curve(b.lam, b.psi, b.d_eff, b.radius, b.height, b.w, n=600, t_max=t_co[-1])
    ax.plot(t_th / 3600, c_th, color=STEEL, lw=1.6, ls=(0, (5, 3)), label="Rosen, as in the thesis")
    ax.plot(t_co / 3600, c_co, color=FROST, lw=2, label="Rosen, corrected")
    ax.plot(sol.t / 3600, sol.c_out, color=INK, lw=1.4, ls=(0, (2, 2)), label="LDF + axial dispersion, corrected")
    ax.axhline(0.05, color=STEEL, lw=0.8, ls=":")
    ax.text(0.02, 0.07, "c/c₀ = 5 %", color=STEEL, transform=ax.get_yaxis_transform(), fontsize=9)

    # capacity / feed straight from the isotherm point, independent of any kinetics
    eq, hyd = corr["equilibrium"], corr["hydraulics"]
    t_mb = eq["av"] * hyd["area"] * corr["bed"].height / (30.0 / 3600.0) / 3600
    ax.axvline(t_mb, color=OCHRE, lw=1.2)
    ax.text(t_mb - 0.04, 0.7, f"capacity / feed\n{t_mb:.2f} h", color=INK, fontsize=9, ha="right")

    ax.set_xlim(0.4, 3.2)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("t [h]")
    ax.set_ylabel("c / c₀ at the outlet")
    ax.set_title("R22 on zeolite 4A, 30 kg/h: thesis model vs corrected", loc="left", color=INK, fontsize=11)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "breakthrough_modes.png")
    plt.close(fig)


def bed_loading_gif() -> None:
    res, _, _, sol = run("corrected", "R32", "13X")
    H = res["bed"].height
    cmap = LinearSegmentedColormap.from_list("load", ["#e4e9e6", OCHRE])
    t_h = sol.t / 3600

    fig, (ax_bed, ax_out) = plt.subplots(2, 1, figsize=(7.2, 3.8), dpi=90,
                                         gridspec_kw={"height_ratios": [1, 2.2]})
    img = ax_bed.imshow(sol.q_profiles[:1], aspect="auto", cmap=cmap, vmin=0, vmax=1,
                        extent=(0, H, 0, 1))
    ax_bed.set_yticks([])
    ax_bed.grid(False)
    ax_bed.set_xlabel("distance from the inlet [m]")
    front = ax_bed.axvline(0, color=SIGNAL, lw=1.5)
    title = ax_bed.set_title("R32 on 13X, t = 0.0 h, bed 0 % loaded", loc="left", color=INK, fontsize=10)

    ax_out.plot(t_h, sol.c_out, color=FROST, lw=2)
    dot, = ax_out.plot([], [], "o", color=SIGNAL, ms=6)
    ax_out.set_xlim(0, t_h[-1])
    ax_out.set_ylim(0, 1.05)
    ax_out.set_xlabel("t [h]")
    ax_out.set_ylabel("outlet c / c₀")
    fig.tight_layout()

    def frame(i: int):
        q = sol.q_profiles[i]
        img.set_data(q[None, :])
        j = np.argmax(q < 0.5) if (q < 0.5).any() else len(q) - 1
        front.set_xdata([sol.zeta[j] * H] * 2)
        t = sol.t_profiles[i]
        c = np.interp(t, sol.t, sol.c_out)
        dot.set_data([t / 3600], [c])
        title.set_text(f"R32 on 13X, t = {t / 3600:.1f} h, bed {q.mean() * 100:.0f} % loaded")
        return img, front, dot, title

    anim = FuncAnimation(fig, frame, frames=len(sol.t_profiles), blit=False)
    anim.save(OUT / "bed_loading.gif", writer=PillowWriter(fps=10))
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    breakthrough_modes()
    bed_loading_gif()
    print("written to", OUT)
