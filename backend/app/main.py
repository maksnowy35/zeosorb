from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router
from .api_process import router as process_router

app = FastAPI(
    title="ZeoSorb API",
    version=__version__,
    description=(
        "Breakthrough of refrigerants through zeolite beds: Rosen analytical solution, "
        "numerical LDF model with axial dispersion, binary separation window, feed line from a "
        "two-phase storage tank and a two-bed pressure/temperature swing cycle."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(process_router, prefix="/api/v1")
