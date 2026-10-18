from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import thesis_calc as tc

app = FastAPI(title="ZeoSorb API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CalcRequest(BaseModel):
    refrigerant: str
    zeolite: str
    mass_flow: float = 30.0   # kg/h
    threshold: float = 0.05   # c/c0


@app.get("/")
def root():
    return {"name": "ZeoSorb", "version": app.version}


@app.get("/refrigerants")
def refrigerants():
    return tc.REFRIGERANTS


@app.get("/zeolites")
def zeolites():
    return tc.ZEOLITES


@app.get("/adsorption")
def adsorption():
    return tc.ADSORPTION


@app.post("/calculate")
def calculate(req: CalcRequest):
    if req.refrigerant not in tc.REFRIGERANTS or req.zeolite not in tc.ZEOLITES:
        raise HTTPException(404, "unknown refrigerant or zeolite")
    try:
        return tc.calculate(req.refrigerant, req.zeolite, req.mass_flow, req.threshold)
    except ValueError as e:
        raise HTTPException(422, str(e))
