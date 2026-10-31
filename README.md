# ZeoSorb

Breakthrough of refrigerants through zeolite beds — a small FastAPI + Angular app built
around my engineering thesis (Politechnika Warszawska, MEiL, 2024/25):

> **„Analiza procesu adsorpcji czynników chłodniczych na wybranych złożach sorpcyjnych”**
> *(Analysis of refrigerant adsorption on selected sorbent beds)*

Recovered refrigerant blends (R410A, R404A, R407C, …) often can't be reused because they're
contaminated or contain components banned in the EU (R22). Rectification doesn't work for
azeotropic blends, adsorption on zeolites might. The thesis estimates **how long a zeolite
column keeps a single refrigerant in** (breakthrough time) for 6 refrigerants and 3 zeolites.
This app turns the Excel sheets from the thesis into something you can click through.

## What it does

- recalculates the whole chain from the thesis for a chosen refrigerant / zeolite pair
- plots the breakthrough curve `c/c0(t)` (Rosen solution)
- compares all pairs at once (matrix of breakthrough times)
- shows every intermediate value (Henry constant, D, D_K, D', Re, Sc, Sh, k_c,g, λ', ψ)

## Calculation chain

```mermaid
flowchart LR
    A[Refrigerant<br/>M, d, μ] --> C[c* = pM/RT]
    B[Zeolite<br/>R, d_pore, ε, ρ_bulk] --> K
    I[Isotherm point<br/>q @ 0.8 bar] --> K[Henry constant<br/>Ka = a_v / c*]
    C --> K
    A --> D[D – kinetic theory]
    B --> DK[D_K – Knudsen]
    D --> DE["D' : 1/D' = 1/D + 1/D_K"]
    DK --> DE
    D --> SH[Re, Sc → Sh → k_c,g]
    K --> R[Rosen parameters<br/>λ', ψ]
    DE --> R
    SH --> R
    R --> T[c/c0 = ½ 1 + erf E<br/>breakthrough time τ]

Rosen parameters and the breakthrough curve:

$$\lambda' = \frac{3 D' K_a H}{z\,w\,R^2}, \qquad \psi = \frac{D' K_a}{R\,k_{c,g}}, \qquad z = \frac{\varepsilon}{1-\varepsilon}$$

$$\frac{c}{c_0} = \frac{1}{2}\left[1 + \operatorname{erf}\left(\frac{\frac{3\tau'}{2\lambda'} - 1}{2\sqrt{\frac{1+5\psi}{5\lambda'}}}\right)\right], \qquad \tau' = \frac{2D'}{R^2}\left(t - \frac{H}{w}\right)$$

## Run

Backend (Python 3.11+):

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload     # http://localhost:8000/docs
pytest
```

Frontend (Node 22+):

```bash
cd frontend
npm install
npm start                         # http://localhost:4200, /api is proxied to :8000
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/materials` | refrigerants, zeolites, isotherm points |
| POST | `/api/breakthrough` | full calculation + curve for one pair |
| GET | `/api/matrix` | breakthrough time for all pairs |

## Data

- refrigerant properties: PubChem / Avogadro (molecule size), CoolProp (viscosity at 100 °C, 0.8 bar)
- zeolites 4A and 13X: my own measurements (bulk density, porosity), 5A: literature
- adsorbed amounts at 0.8 bar: literature isotherms (Wanigarathna et al. 2016, 2017), thesis Tab. 2

## TODO

- [ ] numerical model to check the Rosen approximation
- [ ] binary mixtures (R410A = R32 + R125)
- [ ] Docker
