from typing import Union

from pydantic import BaseModel

from analyst.adapters.binance import BinanceAdapter, BinanceWebSocketAdapter
from analyst.adapters.local_file import LocalFileAdapter
from analyst.adapters.redis import RedisAdapter
from analyst.settings import AppSettings

CacheAdapter = Union[LocalFileAdapter, RedisAdapter]


class Adapters(BaseModel):
    binance: BinanceAdapter
    binance_websocket: BinanceWebSocketAdapter
    cache: CacheAdapter

    class Config:
        arbitrary_types_allowed = True


def get_adapters(settings: AppSettings) -> Adapters:
    cache_adapter: CacheAdapter

    if settings.redis_cache_settings.host:
        redis_adapter = RedisAdapter(**settings.redis_cache_settings.dict())

        if not redis_adapter and not redis_adapter.connected:
            cache_adapter = LocalFileAdapter(dir_path=settings.file_cache_settings.dir)
        else:
            cache_adapter = redis_adapter
    else:
        cache_adapter = LocalFileAdapter(dir_path=settings.file_cache_settings.dir)

    return Adapters(
        binance=BinanceAdapter(settings=settings.binance_settings),
        binance_websocket=BinanceWebSocketAdapter(),
        cache=cache_adapter,
    )
