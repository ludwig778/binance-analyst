from pytest import fixture

from analyst.bot.strategies.base import StrategyState
from tests.mocks.strategies import DummyStrategy


@fixture(scope="function")
def strategies():
    return (
        DummyStrategy.create(),
        DummyStrategy.create(state=StrategyState.stopping),
        DummyStrategy.create(state=StrategyState.stopped),
    )


def test_base_strategy_creation():
    assert DummyStrategy.create()


async def test_base_strategy_pending_stop(strategies, order_manager, controllers):
    await strategies[0].pending_stop(order_manager)

    assert strategies[0].state == StrategyState.stopping

    mongo_strategy = await controllers.mongo.get_strategy(strategy_id=strategies[0].id)

    assert mongo_strategy.dict() == strategies[0].dict()
    assert mongo_strategy.state == StrategyState.stopping

    await strategies[1].pending_stop(order_manager)
    assert strategies[1].state == StrategyState.stopping

    await strategies[2].pending_stop(order_manager)
    assert strategies[2].state == StrategyState.stopped


async def test_base_strategy_stop(strategies, order_manager, controllers):
    await strategies[0].stop(order_manager)

    assert strategies[0].state == StrategyState.stopped

    mongo_strategy = await controllers.mongo.get_strategy(strategy_id=strategies[0].id)

    assert mongo_strategy.dict() == strategies[0].dict()
    assert mongo_strategy.state == StrategyState.stopped

    await strategies[1].stop(order_manager)
    assert strategies[1].state == StrategyState.stopped

    await strategies[2].stop(order_manager)
    assert strategies[2].state == StrategyState.stopped
