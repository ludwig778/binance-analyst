import asyncio

from pytest import fixture

from analyst.bot.bot import Runner
from tests.mocks.order_manager import MockedOrderManager


@fixture(scope="session")
async def controllers(functionnal_controllers):
    return functionnal_controllers


@fixture(scope="session")
async def repositories(functionnal_repositories):
    return functionnal_repositories


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


async def test_bot(controllers):
    order_manager = MockedOrderManager(controllers=controllers)
    await order_manager.setup()

    runner = Runner(controllers=controllers, order_manager=order_manager)

    try:
        await runner.run()
    except asyncio.TimeoutError:
        await controllers.binance.close_streams()
