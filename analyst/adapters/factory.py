from typing import Union

from pydantic import BaseModel

from analyst.adapters.binance import (
    BinanceAdapter,
    BinanceMarketWebSocketAdapter,
    BinanceUserDataWebSocketAdapter,
)
from analyst.adapters.local_file import LocalFileAdapter
from analyst.adapters.mongo import MongoAdapter
from analyst.adapters.rabbitmq import RabbitMQAdapter
from analyst.adapters.redis import RedisAdapter
from analyst.settings import AppSettings

CacheAdapter = Union[LocalFileAdapter, RedisAdapter]


class Adapters(BaseModel):
    binance: BinanceAdapter
    binance_market_websocket: BinanceMarketWebSocketAdapter
    binance_user_data_websocket: BinanceUserDataWebSocketAdapter
    cache: CacheAdapter
    mongo: MongoAdapter
    rabbitmq: RabbitMQAdapter

    class Config:
        arbitrary_types_allowed = True


async def get_adapters(settings: AppSettings) -> Adapters:
    cache_adapter: CacheAdapter

    if settings.redis_cache.host:
        redis_adapter = RedisAdapter(**settings.redis_cache.dict())

        if not redis_adapter and not redis_adapter.connected:
            cache_adapter = LocalFileAdapter(dir_path=settings.file_cache_dir)
        else:
            cache_adapter = redis_adapter
    else:
        cache_adapter = LocalFileAdapter(dir_path=settings.file_cache_dir)

    binance_adapter = BinanceAdapter(settings=settings.binance)
    await binance_adapter.setup_weight()

    return Adapters(
        binance=binance_adapter,
        binance_market_websocket=BinanceMarketWebSocketAdapter(settings=settings.binance),
        binance_user_data_websocket=BinanceUserDataWebSocketAdapter(settings=settings.binance),
        cache=cache_adapter,
        mongo=MongoAdapter(settings=settings.mongo),
        rabbitmq=RabbitMQAdapter(settings=settings.rabbitmq),
    )
