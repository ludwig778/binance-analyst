from typing import Union

from hartware_lib.adapters.directory import DirectoryAdapter
from pydantic import BaseModel

from binance_analyst.adapters.binance import BinanceAdapter
from binance_analyst.adapters.dataframe import DataFrameDirectoryAdapter
from binance_analyst.core.settings import get_settings

AdapterInstance = Union[BinanceAdapter, DirectoryAdapter, DataFrameDirectoryAdapter]


class Adapters(BaseModel):
    binance: BinanceAdapter
    metadata: DirectoryAdapter
    dataframe: DataFrameDirectoryAdapter

    class Config:
        arbitrary_types_allowed = True


def get_adapters() -> Adapters:
    settings = get_settings()

    return Adapters(
        binance=BinanceAdapter(settings=settings.binance_settings),
        metadata=DirectoryAdapter(dir_path=settings.cache_settings.metadata_dir),
        dataframe=DataFrameDirectoryAdapter(dir_path=settings.cache_settings.dataframe_dir),
    )
