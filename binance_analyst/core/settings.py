from os import environ
from pathlib import Path

from pydantic import BaseModel

TESTING: bool = bool(environ.get("BINANCE_ANALYST_TEST"))

CACHE_FOLDER: Path = Path.home() / ("test_cache_dir" if TESTING else "cache_dir")


class BinanceSettings(BaseModel):
    api_url: str = "https://api.binance.com"
    api_key: str = environ["BINANCE_ANALYST_API_KEY"]
    secret_key: str = environ["BINANCE_ANALYST_SECRET_KEY"]


class CacheSettings(BaseModel):
    metadata_path_dir: Path = CACHE_FOLDER / "_metadata"
    dataframe_path_dir: Path = CACHE_FOLDER / "_dataframes"


class Settings(BaseModel):
    testing: bool = TESTING

    binance_settings: BinanceSettings = BinanceSettings()
    cache_settings: CacheSettings = CacheSettings()


def get_settings() -> Settings:
    return Settings()
