from analyst.adapters.binance import BinanceAdapter, BinanceWebSocketAdapter
from analyst.adapters.local_file import LocalFileAdapter
from analyst.adapters.types import Adapters, RedisAdapter, CacheAdapter
from analyst.settings import AppSettings


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
