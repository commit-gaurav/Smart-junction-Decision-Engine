"""
Main entry point for the Smart Junction Decision Engine FastAPI backend.

Provides health checks, API routing, database initialization, and CORS middleware
for the simulation dashboard.
NOTE: This software is a simulation engine and does NOT transmit commands to physical hardware.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.db import init_db, check_db_health
from app.routers import traffic, signals

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Runs repeatable SQLite schema creation and seed initialization on startup.
    """
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Explainable traffic junction decision engine and simulation (does not connect to hardware)",
    version="0.1.0",
    lifespan=lifespan,
)

# Cross-Origin Resource Sharing (CORS) for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(traffic.router)
app.include_router(signals.router)


@app.get("/")
def read_root():
    """Root status summary verifying simulation mode."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "mode": "simulation_only",
        "hardware_transmission": "disabled",
        "docs_url": "/docs",
    }


@app.get("/api/health")
def get_health():
    """
    Health check endpoint matching the PLAN.md API specification.
    Returns status, version, and database connectivity.
    """
    db_status = check_db_health()
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "version": "0.1.0",
        "database": db_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
