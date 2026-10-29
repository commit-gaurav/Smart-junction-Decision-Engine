"""
Main entry point for the Smart Junction Decision Engine FastAPI backend.

Provides health checks, API routing, and CORS middleware for the simulation dashboard.
NOTE: This software is a simulation engine and does NOT transmit commands to physical hardware.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Explainable traffic junction decision engine and simulation (does not connect to hardware)",
    version="0.1.0",
)

# Cross-Origin Resource Sharing (CORS) for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    Returns application status, version, and database readiness.
    """
    return {
        "status": "healthy",
        "version": "0.1.0",
        "database": "uninitialized_skeleton",
        "mode": "simulation_only",
        "transmission_status": "not_sent",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

