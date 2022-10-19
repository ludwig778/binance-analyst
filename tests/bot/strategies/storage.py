from datetime import timedelta
from decimal import Decimal

from pytest import fixture

from analyst.bot.strategies.base import StrategyState
from analyst.bot.strategies.market_maker import MarketMakerV1, MarketMakerV2, MarketMakerV3


@fixture(scope="function", autouse=True)
async def cleanup(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


async def test_all_strategies_instanciation(controllers):
    for strategy in (
        MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal(".002")),
        MarketMakerV1.create(
            symbol="AMPBTC", quote_quantity=Decimal(".002"), state=StrategyState.stopped
        ),
        MarketMakerV1.create(
            symbol="AMPBTC", quote_quantity=Decimal(".002"), state=StrategyState.stopping
        ),
        MarketMakerV2.create(
            symbol="QLCBTC",
            quote_quantity=Decimal(".004"),
        ),
        MarketMakerV3.create(
            symbol="AMPBTC",
            quote_quantity=Decimal(".003"),
            interval=Decimal("300"),
            cleanup_interval=timedelta(hours=1),
            max_buy_orders=3,
            max_increase_step=7,
            max_increase_retain_delta=timedelta(minutes=45),
        ),
    ):
        await controllers.mongo.store_strategy(strategy)

        stored = await controllers.mongo.get_strategy(strategy.id)

        assert strategy.dict() == stored.dict()
