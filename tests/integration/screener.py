import asyncio

from pytest import fixture

from analyst.controllers.factory import Controllers
from analyst.screener import MarketMakerScreener


@fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@fixture(scope="session")
async def controllers(functionnal_controllers):
    return functionnal_controllers


async def test_screener(controllers: Controllers):
    MarketMakerScreener(controllers=controllers)

    print(controllers.binance.adapters.binance.weights)

    return
