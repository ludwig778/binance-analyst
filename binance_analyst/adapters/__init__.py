from typing import Union

from pydantic import BaseModel

from binance_analyst.adapters.binance import BinanceAdapter
from binance_analyst.adapters.dataframe import DataFrameFileAdapter
from binance_analyst.adapters.file import FileAdapter
from binance_analyst.core.settings import get_settings

AdapterInstance = Union[BinanceAdapter, DataFrameFileAdapter, FileAdapter]


class Adapters(BaseModel):
    binance: BinanceAdapter
    metadata: FileAdapter
    dataframe: DataFrameFileAdapter

    class Config:
        arbitrary_types_allowed = True


def get_adapters() -> Adapters:
    settings = get_settings()

    return Adapters(
        binance=BinanceAdapter(settings=settings.binance_settings),
        metadata=DirectoryAdapter(dir_path=settings.cache_settings.metadata_dir),
        dataframe=DataFrameDirectoryAdapter(dir_path=settings.cache_settings.dataframe_dir),
    )
