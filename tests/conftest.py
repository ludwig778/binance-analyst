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
