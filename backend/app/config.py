"""
Application Configuration and Demo Settings.

NOTE: The timing parameters defined below are approved editable software-demo
values for the four-way junction simulation. They are NOT certified
road-engineering recommendations or traffic-control design guidance.
"""

from typing import List, Optional
import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class Settings(BaseSettings):
        # App identity and environment
        app_name: str = "Smart Junction Decision Engine"
        app_env: str = "development"
        debug: bool = False
        api_prefix: str = "/api"

        # Server network settings
        host: str = "127.0.0.1"
        port: int = 8000
        cors_origins: List[str] = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

        # Persistence
        database_url: str = "sqlite:///./backend/data/junction.db"

        # Approved software-demo timing defaults (seconds)
        # Editable demo defaults; NOT road-engineering guidance
        min_green_seconds: int = Field(default=8, description="Minimum green duration")
        max_green_seconds: int = Field(default=45, description="Maximum green duration")
        yellow_seconds: int = Field(default=3, description="Yellow clearance duration")
        all_red_seconds: int = Field(default=1, description="All-red clearance duration")
        fairness_max_wait_seconds: int = Field(
            default=90, description="Fairness maximum waiting time ceiling"
        )
        planning_tick_seconds: int = Field(
            default=1, description="Frequency of simulation engine clock tick"
        )
        stale_threshold_seconds: int = Field(
            default=30, description="Freshness window for observations before flagged stale"
        )

        # Optional Model Configuration (pre-trained YOLO video vehicle detector)
        # Manual counts and seeded simulation operate independently of this setting.
        yolo_model_path: Optional[str] = Field(
            default=None, description="Path or identifier for pretrained YOLO weights"
        )
        yolo_confidence_threshold: float = Field(
            default=0.25, description="Detection confidence cutoff threshold"
        )

        model_config = {
            "env_file": ".env",
            "env_file_encoding": "utf-8",
            "extra": "ignore",
        }

except ImportError:
    # Graceful fallback if pydantic_settings is not yet installed in the current environment
    class Settings:  # type: ignore
        app_name: str = "Smart Junction Decision Engine"
        app_env: str = os.getenv("APP_ENV", "development")
        debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")
        api_prefix: str = "/api"

        host: str = os.getenv("HOST", "127.0.0.1")
        port: int = int(os.getenv("PORT", "8000"))
        cors_origins: List[str] = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")

        database_url: str = os.getenv(
            "DATABASE_URL", "sqlite:///./backend/data/junction.db"
        )

        # Approved software-demo timing defaults (seconds)
        # Editable demo defaults; NOT road-engineering guidance
        min_green_seconds: int = int(os.getenv("MIN_GREEN_SECONDS", "8"))
        max_green_seconds: int = int(os.getenv("MAX_GREEN_SECONDS", "45"))
        yellow_seconds: int = int(os.getenv("YELLOW_SECONDS", "3"))
        all_red_seconds: int = int(os.getenv("ALL_RED_SECONDS", "1"))
        fairness_max_wait_seconds: int = int(
            os.getenv("FAIRNESS_MAX_WAIT_SECONDS", "90")
        )
        planning_tick_seconds: int = int(os.getenv("PLANNING_TICK_SECONDS", "1"))
        stale_threshold_seconds: int = int(os.getenv("STALE_THRESHOLD_SECONDS", "30"))

        # Optional Model Configuration
        yolo_model_path: Optional[str] = os.getenv("YOLO_MODEL_PATH", None) or None
        yolo_confidence_threshold: float = float(
            os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.25")
        )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()

