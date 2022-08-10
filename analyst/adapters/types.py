from typing import Union

from pydantic import BaseModel

from analyst.adapters.binance import BinanceAdapter, BinanceWebSocketAdapter
from analyst.adapters.local_file import LocalFileAdapter
from analyst.adapters.redis import RedisAdapter

CacheAdapter = Union[LocalFileAdapter, RedisAdapter]


class Adapters(BaseModel):
    binance: BinanceAdapter
    binance_websocket: BinanceWebSocketAdapter
    cache: CacheAdapter

    class Config:
        arbitrary_types_allowed = True
