import asyncio
from os import environ

from pytest import fixture

from analyst.adapters.factory import get_adapters
from analyst.bot.order_manager import OrderManager
from analyst.controllers.factory import get_controllers
from analyst.repositories.factory import get_repositories
from analyst.settings import get_settings
from tests.mocks.order_manager import MockedOrderManager
from tests.mocks.strategies import DummyStrategy  # noqa # pylint: disable=unused-import


@fixture(scope="session")
def show_itg_data():
    return environ.get("SHOW_INTEGRATION_DATA", False)


@fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@fixture(scope="function")
def settings(monkeypatch):
    monkeypatch.setenv("ANALYST_BINANCE_API_KEY", "api_key")
    monkeypatch.setenv("ANALYST_BINANCE_SECRET_KEY", "secret_key")

    return get_settings()


@fixture(scope="function")
async def adapters(settings):
    return await get_adapters(settings=settings)


@fixture(scope="function")
async def repositories(settings, adapters):
    return get_repositories(settings=settings, adapters=adapters)


@fixture(scope="function")
def controllers(adapters, repositories):
    return get_controllers(adapters=adapters, repositories=repositories)


@fixture(scope="session")
async def functionnal_settings():
    settings = get_settings()
    settings.test = False

    return settings


@fixture(scope="session")
async def functionnal_adapters(functionnal_settings):
    return await get_adapters(settings=functionnal_settings)


@fixture(scope="session")
async def functionnal_repositories(functionnal_settings, functionnal_adapters):
    return get_repositories(settings=functionnal_settings, adapters=functionnal_adapters)


@fixture(scope="session")
async def functionnal_controllers(functionnal_adapters, functionnal_repositories):
    return get_controllers(adapters=functionnal_adapters, repositories=functionnal_repositories)


@fixture(scope="function")
def binance_controller(controllers):
    return controllers.binance


@fixture(scope="function")
def mongo_controller(controllers):
    return controllers.mongo


@fixture(scope="function")
def order_manager(controllers):
    return MockedOrderManager(controllers=controllers)


@fixture(scope="function")
def functionnal_order_manager(controllers):
    return OrderManager(controllers=controllers)
