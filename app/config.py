"""Ground fire enhancement system configuration.

Network-dependent services only: FIRMS historical, OSM industrial, Nominatim geocoding.
No landcover LR/names — those come from the satellite result.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # FIRMS API
    firms_map_key: str = "DEMO_KEY"
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

    # OSM Overpass
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Nominatim
    nominatim_url: str = "https://nominatim.openstreetmap.org/reverse"

    # Confidence weights (ground only adds historical + industrial)
    beta_hist: float = 0.3

    # False positive penalty (ground only has industrial detector)
    fp_penalty_industrial: float = 0.8

    # Cache settings
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 1000

    # DB
    db_path: str = "data/fire_ground.db"

    # Data directories
    data_dir: Path = Path("data")

    # HTTP client
    http_timeout: float = 10.0

    model_config = {"env_prefix": "GROUND_", "env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
