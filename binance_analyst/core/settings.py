from pathlib import Path

from hartware_lib.pydantic.field_types import BooleanFromString
from pydantic import BaseSettings, Field

DEFAULT_METADATA_CACHE_DIR = Path("cache_dir", "metadata")
DEFAULT_DATAFRAME_CACHE_DIR = Path("cache_dir", "dataframes")


class BinanceApiSettings(BaseSettings):
    api_url: str = "https://api.binance.com"
    api_key: str
    secret_key: str

    class Config:
        case_sensitive = False
        env_prefix = "BINANCE_ANALYST_"


class CacheSettings(BaseSettings):
    metadata_dir: Path = DEFAULT_METADATA_CACHE_DIR
    dataframe_dir: Path = DEFAULT_DATAFRAME_CACHE_DIR

    class Config:
        case_sensitive = False
        env_prefix = "BINANCE_ANALYST_"


class AppSettings(BaseSettings):
    test: BooleanFromString = Field(default=False)
    debug: BooleanFromString = Field(default=False)

    cache_settings: CacheSettings = Field(default_factory=CacheSettings)
    binance_settings: BinanceApiSettings = Field(default_factory=BinanceApiSettings)

    class Config:
        case_sensitive = False
        env_prefix = "BINANCE_ANALYST_"


def get_settings() -> AppSettings:
    return AppSettings()
