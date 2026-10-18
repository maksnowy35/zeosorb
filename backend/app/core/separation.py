"""
Binary separation estimate from two single-component breakthrough curves.

The component with the lower Henry constant (weak) leaves the bed first. Between the
moment it is fully through (c/c0 >= 0.95) and the moment the strong one starts to break
through (c/c0 = threshold), the outlet carries only the weak component - that's the
"product window". Single-component curves are only overlaid: no competitive adsorption,
no roll-up of the weak component, so treat it as an optimistic first estimate.
"""
from dataclasses import dataclass

from . import pipeline, rosen

FULL_BREAKTHROUGH = 0.95


@dataclass
class PairResult:
    zeolite: str
    weak: str
    strong: str
    alpha: float              # Ka(strong) / Ka(weak)
    t_weak_full: float        # s, weak component at c/c0 = 0.95
    t_strong_break: float     # s, strong component at c/c0 = threshold
    window: float             # s, t_strong_break - t_weak_full (negative = overlap)
    results: dict[str, dict]  # pipeline.run() output per refrigerant


def evaluate(a: str, b: str, base: pipeline.BedInput, threshold: float) -> PairResult:
    """base.refrigerant is ignored, a and b are run on base.zeolite."""
    res = {}
    for ref in (a, b):
        inp = pipeline.BedInput(**{**base.__dict__, "refrigerant": ref, "thresholds": (threshold, FULL_BREAKTHROUGH)})
        res[ref] = pipeline.run(inp)

    weak, strong = sorted((a, b), key=lambda r: res[r]["equilibrium"]["Ka"])
    t_weak = res[weak]["breakthrough"][f"{FULL_BREAKTHROUGH:g}"]
    t_strong = res[strong]["breakthrough"][f"{threshold:g}"]
    return PairResult(
        zeolite=base.zeolite,
        weak=weak,
        strong=strong,
        alpha=res[strong]["equilibrium"]["Ka"] / res[weak]["equilibrium"]["Ka"],
        t_weak_full=t_weak,
        t_strong_break=t_strong,
        window=t_strong - t_weak,
        results=res,
    )


def curve_for(result: dict, n: int = 300, t_max: float | None = None):
    bed = result["bed"]
    return rosen.curve(bed.lam, bed.psi, bed.d_eff, bed.radius, bed.height, bed.w, n=n, t_max=t_max)
