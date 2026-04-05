from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from . import models

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Follow The Money — AusPol Transparency API",
    description="Public API for Australian political donations, expenditure, and voting records.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers will be added per phase
# from .routers import donors, parties, politicians
# app.include_router(donors.router, prefix="/api/v1")
# app.include_router(parties.router, prefix="/api/v1")
# app.include_router(politicians.router, prefix="/api/v1")
