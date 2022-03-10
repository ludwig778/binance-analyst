from datetime import datetime

from pytest import fixture

from binance_analyst.adapters import get_adapters
from binance_analyst.controllers import get_controllers
from binance_analyst.settings import get_settings
from tests.fixtures import *  # noqa


@fixture(scope="function")
def settings():
    return get_settings()


@fixture(scope="function")
def adapters(settings):
    return get_adapters(settings=settings)


@fixture(scope="function")
def controllers(adapters):
    return get_controllers(adapters=adapters)


@fixture(scope="session")
def dataframes_1d():
    settings = get_settings()
    adapters = get_adapters(settings=settings)
    pair_repo = get_controllers(adapters=adapters).pair

    pairs = pair_repo.load()

    yield pair_repo.load_dataframes(
        pairs,
        interval="1d",
        start_datetime=datetime(2017, 1, 1),
        end_datetime=datetime(2022, 1, 1),
    )
