from pandas import DataFrame, date_range
from pytest import fixture

from analyst.adapters.redis import RedisAdapter
from analyst.settings import get_settings
from tests.utils import equal_dataframes


@fixture(scope="function")
def redis_adapter(monkeypatch):
    monkeypatch.setenv("ANALYST_REDIS_HOST", "redis")
    monkeypatch.setenv("ANALYST_REDIS_DB", "1")

    settings = get_settings()

    return RedisAdapter(**settings.redis_cache_settings.dict())


@fixture(scope="function", autouse=True)
def clean(redis_adapter):
    if keys := redis_adapter.keys("*"):
        redis_adapter.delete(*keys)

    yield

    if keys := redis_adapter.keys("*"):
        redis_adapter.delete(*keys)


def test_redis_adapter_exists_and_delete(redis_adapter):
    assert not redis_adapter.exists("some_key")

    redis_adapter.save("some_key", {"some": "data"})

    assert redis_adapter.exists("some_key")

    redis_adapter.delete("some_key")

    assert not redis_adapter.exists("some_key")


def test_redis_adapter_save_and_read(redis_adapter):
    test_data = {"test": "data"}

    redis_adapter.save("some_key", test_data)

    stored_data = redis_adapter.read("some_key")

    assert test_data == stored_data


def test_redis_adapter_save_and_read_dataframe(redis_adapter):
    test_df = DataFrame({"a": [1, 3, 5], "b": [2, 4, 6]})
    test_df["timestamp"] = date_range("2022-01-01", "2022-01-03", freq="D")
    test_df.set_index("timestamp", inplace=True)

    redis_adapter.save_dataframe("some_key", test_df)

    stored_df = redis_adapter.read_dataframe("some_key")

    assert equal_dataframes(test_df, stored_df)
