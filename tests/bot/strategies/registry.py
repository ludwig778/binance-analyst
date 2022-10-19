from analyst.bot.strategies.base import Strategy
from analyst.bot.strategies.factory import get_strategy
from analyst.bot.strategies.registry import RegisteredStrategy


async def test_lmao():
    class DummyStrategy(Strategy):
        name = "dummy"
        version = "v1"

    registered = RegisteredStrategy.instances["dummy:v1"]

    assert registered

    from_factory = get_strategy("dummy", "v1")

    assert from_factory

    assert registered is from_factory
