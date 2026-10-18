from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router

app = FastAPI(
    title="ZeoSorb API",
    version=__version__,
    description="Breakthrough of refrigerants through zeolite beds (Rosen model).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
