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

    # FIRMS likelihood ratios per FirmsMatchLevel (used as ln(LR) in logit space)
    firms_lr_exact_match: float = 4.0
    firms_lr_nearby: float = 2.5
    firms_lr_regional: float = 1.5
    firms_lr_no_history: float = 0.5

    # Industrial facility delta per IndustrialProximity (logit space)
    industrial_delta_within_500m: float = -2.5
    industrial_delta_within_2km: float = -1.5
    industrial_delta_within_5km: float = -0.8
    industrial_delta_none: float = 0.3

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
