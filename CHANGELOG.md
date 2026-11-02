# Changelog

## [1.1.0]

### Added
- **Feed line** (`POST /api/v1/feed`, page *Feed line*): two-phase storage tank (vapour or liquid withdrawal, ambient
  gain, heater), isenthalpic reducer, heated or cooled pipe segments (jacket, electric trace, insulated, bare) with
  Gnielinski / Hausen, Gungor-Winterton and Shah coefficients and Churchill friction; campaign over hours; fractionation
  of zeotropic blends; capacity and viscosity against feed temperature; findings
- `POST /api/v1/feed/solve`: jacket temperature or trace power for a target temperature at the adsorber
- **Cycle** (`POST /api/v1/cycle`, page *Cycle*): two beds, non-isothermal, extended Langmuir with temperature
  dependence, LDF kinetics from the corrected grain model (macropores, local isotherm slope), shared feed header,
  vacuum source with a floor, purge, jackets limited by radial conduction; setpoints as controller targets or step
  transitions; cyclic steady state with extrapolation; KPIs, step table and findings
- step presets: a typical 10-step two-bed sequence and a 4-step Skarstrom cycle (`app/data/cycles.json`)
- temperature-dependent isotherms anchored to the thesis points (`app/data/isotherms.json`)
- CoolProp as a dependency; figures for the feed line and the cycle

### Fixed
- trace heating that overheats the gas no longer crashes the setting solver


## [1.0.0]

### Added
- numerical column model: LDF + axial dispersion solved with the method of lines (`app/core/ldf.py`),
  validated against the Rosen solution and by a mass balance
- concentration and loading profiles along the bed, animated column drawing in the UI
- spreading budget: how much of the front width comes from diffusion into grains vs axial dispersion
- separation of blends (`POST /api/v1/separation`): common gas velocity, product window, ranking of beds;
  presets for R410A, R507A, R407C, R404A
- parameter sweep (`POST /api/v1/sweep`) and sensitivity chart
- `mode` parameter: `corrected` (default) or `thesis` (reproduces the thesis tables)
- grain model in corrected mode: diffusion through the binder macropores (molecular + Knudsen in series, tortuosity),
  mapped onto Rosen's grain diffusion as `K D' = eps_M D_p`; macropore data from Hu et al. (2014)
- molecular diffusion from Chapman–Enskog (`rho D / mu = 1.32`) in corrected mode
- raw grain data from thesis ch. 4 (`V_k`, `m_k`, `v_p`) and the bed structure derived from it
- pore tortuosity factor, default of the mode when not given (`null`)
- both modes side by side with the source of every value (`audit` in the breakthrough response, table in the simulator)
- compare page: heatmap of breakthrough time / Henry constant / front width
- model page with equations, an audit of the thesis model, limitations and sources
- Docker Compose setup, GitHub Actions CI, figures script (`scripts/make_figures.py`)

### Fixed
- Knudsen diffusivity: pore diameter was converted from Å with 1e-8 instead of 1e-10 (D_K, D' ~100x too high);
  kept in thesis mode, and corrected mode no longer takes Knudsen in the zeolite window at all (see the grain model)
- film coefficient now from the Wakao–Funazkri correlation with the grain diameter (corrected mode)
- bed capacity: the Henry constant per bed volume was used in the Rosen groups, which are per grain volume, so the bed
  held `(1 - eps)` of its capacity; corrected mode uses `K = Ka / (1 - eps) + eps_M` and its stoichiometric time
  equals capacity / feed (tested)
- voidage between the grains: the thesis value counts the zeolite micropores too; corrected mode takes
  `1 - rho_n / (m_k / V_k)` from the same measurements

### Changed
- **breaking:** all endpoints moved to `/api/v1`, `t_breakthrough` and `curves` are now per model
- frontend rewritten: routing, lazy pages, signals, self-hosted fonts

## [0.0.5]

### Added
- breakthrough curve `c/c0(t)` from the Rosen solution + chart in the UI
- comparison matrix of breakthrough times for all refrigerant / zeolite pairs (`GET /api/matrix`)
- bed height, column diameter and any breakthrough criterion (slider) as inputs
- pytest suite (values checked against the thesis tables)

### Changed
- backend split into `app/core` modules, material data moved to `app/data/*.json`
- `E(c/c0)` from `scipy.special.erfinv` instead of the lookup table (Tab. 12)
- all endpoints under `/api`, frontend uses the dev-server proxy

## [0.0.1]

- first version: Python port of the thesis spreadsheets + simple Angular form
