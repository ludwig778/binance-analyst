from os import environ
from pathlib import Path

from pydantic import BaseModel


class BinanceSettings(BaseModel):
    api_url: str = "https://api.binance.com"
    api_key: str = environ["BINANCE_ANALYST_API_KEY"]
    secret_key: str = environ["BINANCE_ANALYST_SECRET_KEY"]


class CacheSettings(BaseModel):
    metadata_path_dir: Path
    dataframe_path_dir: Path


class Settings(BaseModel):
    testing: bool

    cache_settings: CacheSettings
    binance_settings: BinanceSettings = BinanceSettings()


def get_settings() -> Settings:
    testing: bool = bool(environ.get("BINANCE_ANALYST_TEST"))

    cache_folder: Path = Path("tests", "fixtures") if testing else Path("/", "app", "cache_dir")

    return Settings(
        testing=testing,
        cache_settings={
            "metadata_path_dir": cache_folder / "metadata",
            "dataframe_path_dir": cache_folder / "dataframes",
        },
    )
