# ZeoSorb

Small app built around my engineering thesis (PW, MEiL 2024/25):
**"Analiza procesu adsorpcji czynników chłodniczych na wybranych złożach sorpcyjnych"**
(analysis of refrigerant adsorption on selected sorbent beds).

The backend recalculates the whole chain from chapters 5–6 of the thesis
(Henry constant, diffusion coefficients, Sherwood number, Rosen parameters) and returns
the breakthrough time of a single refrigerant (R32, R22, R134a, R143a, R125, R152a)
through a bed of zeolite 4A, 5A or 13X.

## Run

Backend (Python 3.11+):

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (Node 22+):

```bash
cd frontend
npm install
npm start
```

Open http://localhost:4200

## TODO

- [ ] breakthrough curve plot, not only one time
- [x] move data out of the python file
- [ ] tests
