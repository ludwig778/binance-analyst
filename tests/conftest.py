from datetime import datetime

from pytest import fixture

from binance_analyst.adapters import get_adapters
from binance_analyst.core.settings import get_settings
from binance_analyst.repositories import get_repositories
from tests.fixtures import *  # noqa


@fixture(scope="function")
def settings():
    return get_settings()


@fixture(scope="function")
def adapters():
    return get_adapters()


@fixture(scope="function")
def repositories():
    return get_repositories()


@fixture(scope="session")
def dataframes_1d():
    pair_repo = get_repositories().pair

    pairs = pair_repo.load()

    yield pair_repo.load_dataframes(
        pairs,
        interval="1d",
        start_datetime=datetime(2017, 1, 1),
        end_datetime=datetime(2022, 1, 1),
    )
