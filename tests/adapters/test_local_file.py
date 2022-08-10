from pandas import DataFrame, date_range
from pytest import fixture

from analyst.adapters.local_file import LocalFileAdapter
from analyst.settings import get_settings
from tests.utils import equal_dataframes


@fixture(scope="function")
def local_file_adapter(monkeypatch):
    monkeypatch.setenv("ANALYST_CACHE_DIR", "tests/_generated")

    settings = get_settings()

    return LocalFileAdapter(dir_path=settings.file_cache_settings.dir)


@fixture(scope="function", autouse=True)
def clean(local_file_adapter):
    local_file_adapter.delete_dir()
    local_file_adapter.create_dir()

    yield

    local_file_adapter.delete_dir()


def test_local_file_adapter_exists_and_delete(local_file_adapter):
    assert not local_file_adapter.exists("some_file")

    local_file_adapter.save("some_file", {"some": "data"})

    assert local_file_adapter.exists("some_file")

    local_file_adapter.delete("some_file")

    assert not local_file_adapter.exists("some_file")


def test_local_file_adapter_save_and_read(local_file_adapter):
    test_data = {"test": "data"}

    local_file_adapter.save("some_file", test_data)

    stored_data = local_file_adapter.read("some_file")

    assert test_data == stored_data


def test_local_file_adapter_save_and_read_dataframe(local_file_adapter):
    test_df = DataFrame({"a": [1, 3, 5], "b": [2, 4, 6]})
    test_df["timestamp"] = date_range("2022-01-01", "2022-01-03", freq="D")
    test_df.set_index("timestamp", inplace=True)

    local_file_adapter.save_dataframe("some_file", test_df)

    stored_df = local_file_adapter.read_dataframe("some_file")

    assert equal_dataframes(test_df, stored_df)
