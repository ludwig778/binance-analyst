from pathlib import Path
from typing import Optional

from hartware_lib.pydantic.field_types import BooleanFromString
from pydantic import BaseSettings, Field

DEFAULT_CACHE_DIR = Path("cache_dir", "files")


class BinanceApiSettings(BaseSettings):
    api_url: str = "https://api.binance.com"
    api_key: str
    secret_key: str

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_BINANCE_"


class RedisCacheSettings(BaseSettings):
    host: Optional[str]
    port: int = 6379
    db: int = 0

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_REDIS_"


class FileCacheSettings(BaseSettings):
    dir: Path = DEFAULT_CACHE_DIR

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_CACHE_"


class AppSettings(BaseSettings):
    test: BooleanFromString = Field(default=False)
    debug: BooleanFromString = Field(default=False)

    file_cache_settings: FileCacheSettings = Field(default_factory=FileCacheSettings)
    redis_cache_settings: RedisCacheSettings = Field(default_factory=RedisCacheSettings)
    binance_settings: BinanceApiSettings = Field(default_factory=BinanceApiSettings)

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_"


def get_settings() -> AppSettings:
    return AppSettings()
