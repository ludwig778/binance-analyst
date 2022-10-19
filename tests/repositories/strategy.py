from decimal import Decimal
from uuid import uuid4

from pytest import fixture, raises

from analyst.bot.strategies.base import StrategyState
from analyst.bot.strategies.market_maker import MarketMakerV1
from analyst.repositories.strategy import StrategyAlreadyExist, StrategyDoesNotExist


@fixture(scope="function")
async def repositories(repositories):
    await repositories.strategies.delete_all()

    yield repositories

    await repositories.strategies.delete_all()


async def test_create_strategy(repositories):
    strategy = repositories.strategies._create_strategy(
        {
            "name": "market_maker",
            "version": "v1",
            "args": {"symbol": "AMPBTC", "quote_quantity": "0.004"},
        }
    )

    assert strategy


async def test_create_strategy_exception(repositories):
    with raises(Exception, match="Strategy blank:v0 does not exists"):
        repositories.strategies._create_strategy({"name": "blank", "version": "v0", "args": {}})


async def test_create(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"))

    assert await repositories.strategies.create(strategy)


async def test_create_exception(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"))

    await repositories.strategies.create(strategy)

    with raises(StrategyAlreadyExist, match=f"Strategy {strategy.id} already exists"):
        await repositories.strategies.create(strategy)


async def test_update(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"))

    assert await repositories.strategies.create(strategy)

    strategy.state = StrategyState.stopping
    strategy.flags = MarketMakerV1.Flags.price_going_down

    await repositories.strategies.update(strategy)

    updated = await repositories.strategies.get_by_id(strategy.id)

    assert strategy.dict() == updated.dict()


async def test_update_exception(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"), state=True)

    with raises(StrategyDoesNotExist, match=f"Strategy with id={str(strategy.id)} doesn't exists"):
        await repositories.strategies.update(strategy)


async def test_list(repositories):
    for strategy in (
        MarketMakerV1.create(
            symbol="AMPBTC", quote_quantity=Decimal("0.004"), state=StrategyState.running
        ),
        MarketMakerV1.create(
            symbol="QLCBTC",
            quote_quantity=Decimal("0.004"),
            state=StrategyState.stopping,
            flags=MarketMakerV1.Flags.price_going_down,
        ),
    ):
        await repositories.strategies.create(strategy)

    strategies = await repositories.strategies.list()

    assert len(strategies) == 2

    strategies = await repositories.strategies.list(state=StrategyState.running)

    assert len(strategies) == 1

    strategies = await repositories.strategies.list(state=StrategyState.stopped)

    assert len(strategies) == 0

    strategies = await repositories.strategies.list(flags=MarketMakerV1.Flags.price_going_down)

    assert len(strategies) == 1

    strategies = await repositories.strategies.list(flags=MarketMakerV1.Flags.no_flags)

    assert len(strategies) == 1

    strategies = await repositories.strategies.list(limit=1)

    assert len(strategies) == 1

    strategies = await repositories.strategies.list(flags={"$in": [0]})

    assert len(strategies) == 1


async def test_get_by_id(repositories):
    strategy = await repositories.strategies.create(
        MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"), running=True)
    )

    assert await repositories.strategies.get_by_id(strategy.id)


async def test_get_by_id_exception(repositories):
    id = uuid4()

    with raises(StrategyDoesNotExist, match=f"Strategy with id={str(id)} doesn't exists"):
        await repositories.strategies.get_by_id(id)


async def test_delete(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"), running=True)

    await repositories.strategies.create(strategy)

    assert len(await repositories.strategies.list()) == 1

    await repositories.strategies.delete(strategy)

    assert len(await repositories.strategies.list()) == 0


async def test_delete_exception(repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"), running=True)

    with raises(StrategyDoesNotExist, match="Strategy market_maker:v1 on AMPBTC doesn't exists"):
        await repositories.strategies.delete(strategy)


async def test_delete_all(repositories):
    await repositories.strategies.create(
        MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal("0.004"), running=True)
    )
    await repositories.strategies.create(
        MarketMakerV1.create(symbol="QLCBTC", quote_quantity=Decimal("0.004"), running=True)
    )

    assert len(await repositories.strategies.list()) == 2

    await repositories.strategies.delete_all()

    assert len(await repositories.strategies.list()) == 0
