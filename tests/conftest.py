from pytest import fixture

from analyst.adapters import LocalFileAdapter, RedisAdapter, get_adapters
from analyst.settings import get_settings


@fixture(scope="function")
def settings():
    return get_settings()


@fixture(scope="function")
def adapters(settings):
    return get_adapters(settings=settings)


@fixture(scope="function")
def redis_adapter(settings):
    return RedisAdapter(**settings.redis_cache_settings.dict())


@fixture(scope="function")
def local_file_adapter(settings):
    return LocalFileAdapter(dir_path=settings.file_cache_settings.dir)
