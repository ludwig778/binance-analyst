from copy import copy, deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pytest import fixture, raises

from analyst.bot.strategies.base import StrategyState
from analyst.bot.strategies.market_maker import MarketMakerV1
from analyst.crypto.models import Order
from analyst.repositories.strategy import StrategyDoesNotExist
from tests.fixtures.orders import ORDER_1, ORDER_2, ORDER_3


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


async def create_bunch_of_strategies(repositories):
    for strategy in (
        MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal(".002")),
        MarketMakerV1.create(
            symbol="QLCBTC", quote_quantity=Decimal(".004"), state=StrategyState.stopped
        ),
        MarketMakerV1.create(
            symbol="AMPBTC", quote_quantity=Decimal(".003"), state=StrategyState.stopping
        ),
        MarketMakerV1.create(
            symbol="AMPBTC",
            quote_quantity=Decimal(".003"),
            state=StrategyState.running,
            flags=MarketMakerV1.Flags.price_going_down,
        ),
    ):
        await repositories.strategies.create(strategy)


async def create_strategy_with_orders(repositories):
    strategy = MarketMakerV1.create(
        symbol="ETHBTC", quote_quantity=Decimal(".002"), state=StrategyState.running
    )

    await repositories.strategies.create(strategy)

    for order in (ORDER_1, ORDER_2):
        order = deepcopy(order)
        order.strategy_id = strategy.id

        await repositories.orders.create(order)

    await repositories.orders.create(ORDER_3)


async def test_store_strategy(mongo_controller):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC", quote_quantity=Decimal(".00080218"), state=StrategyState.running
    )
    strategy2 = MarketMakerV1.create(
        symbol="AMPBTC", quote_quantity=Decimal(".00080218"), state=StrategyState.running
    )

    await mongo_controller.store_strategy(strategy)
    await mongo_controller.store_strategy(strategy2)

    strategy.flags = MarketMakerV1.Flags.price_going_down

    await mongo_controller.store_strategy(strategy)

    assert len(await mongo_controller.get_running_strategies()) == 2


async def test_update_strategy(mongo_controller, repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal(".00080218"))

    await repositories.strategies.create(strategy)

    strategy.flags = MarketMakerV1.Flags.price_going_down
    strategy.state = StrategyState.stopping

    await mongo_controller.update_strategy(strategy)

    updated = await repositories.strategies.get_by_id(strategy.id)

    assert strategy.dict() == updated.dict()


async def test_delete_strategy(mongo_controller, repositories):
    strategy = MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal(".00080218"))

    assert await repositories.strategies.create(strategy)

    assert await mongo_controller.delete_strategy(strategy)
    assert not await mongo_controller.delete_strategy(strategy)

    with raises(StrategyDoesNotExist, match=f"Strategy with id={strategy.id} doesn't exists"):
        await repositories.strategies.get_by_id(strategy.id)


async def test_get_strategy(mongo_controller, repositories):
    await create_bunch_of_strategies(repositories)

    strategies = await mongo_controller.get_strategies()

    assert await mongo_controller.get_strategy(strategies[0].id)
    assert not await mongo_controller.get_strategy(uuid4())


async def test_get_strategies(mongo_controller, repositories):
    await create_bunch_of_strategies(repositories)

    strategies = await mongo_controller.get_strategies()

    assert len(strategies) == 4


async def test_get_running_strategies(mongo_controller, repositories):
    await create_bunch_of_strategies(repositories)

    strategies = await mongo_controller.get_running_strategies()

    assert len(strategies) == 3


async def test_get_strategy_last_order(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    strategy = (await repositories.strategies.list())[0]

    last_order = await mongo_controller.get_strategy_last_order(strategy)

    fixture_order = copy(ORDER_2)
    fixture_order.strategy_id = strategy.id

    assert last_order == fixture_order


async def test_strategy_orders(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    strategy = (await mongo_controller.get_running_strategies())[0]

    orders = await mongo_controller.get_strategy_orders(strategy)

    assert len(orders) == 2


async def test_store_order(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    strategy = (await mongo_controller.get_running_strategies())[0]

    now = datetime.now()
    base_order = Order(
        id=4,
        symbol="ETHBTC",
        status="NEW",
        type="MARKET",
        side="BUY",
        price=0.0,
        stop_price=0.0,
        time_in_force="GTC",
        requested_quantity=2.0,
        executed_quantity=0.0,
        created_at=now,
        updated_at=now,
    )

    await mongo_controller.store_order(base_order)

    order = await repositories.orders.get(base_order.id, base_order.symbol)

    assert order.strategy_id is None

    await mongo_controller.store_order(order, strategy)

    order = await repositories.orders.get(order.id, order.symbol)

    assert order.strategy_id == strategy.id

    await mongo_controller.store_order(base_order)

    order = await repositories.orders.get_by_id(base_order.internal_id)

    assert order.strategy_id is None

    now2 = datetime.now()
    duplicate_order = Order(
        id=4,
        symbol="ETHBTC",
        status="NEW",
        type="MARKET",
        side="BUY",
        price=0.0,
        stop_price=0.0,
        time_in_force="GTC",
        requested_quantity=2.0,
        executed_quantity=0.0,
        created_at=now,
        updated_at=now2,
    )

    await mongo_controller.store_order(duplicate_order)

    orders = await repositories.orders.list(id=duplicate_order.id, symbol=duplicate_order.symbol)

    assert len(orders) == 1
    assert orders[0].updated_at == now2


async def test_update_order(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    strategy = (await mongo_controller.get_running_strategies())[0]

    order = await repositories.orders.get(ORDER_3.id, ORDER_3.symbol)
    order.status = "CANCELLED"

    await mongo_controller.update_order(order)

    order = await repositories.orders.get(ORDER_3.id, ORDER_3.symbol)

    assert order.status == "CANCELLED"

    await mongo_controller.update_order(order, strategy)

    order = await repositories.orders.get(ORDER_3.id, ORDER_3.symbol)

    assert order.strategy_id == strategy.id


async def test_get_orders(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    strategy = (await mongo_controller.get_running_strategies())[0]

    orders = await mongo_controller.get_orders()

    assert len(orders) == 3

    orders = await mongo_controller.get_orders(strategy_id=strategy.id)

    assert len(orders) == 2


async def test_get_order(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    assert await mongo_controller.get_order(1, "ETHBTC")

    assert not await mongo_controller.get_order(33, "ETHBTC")


async def test_get_order_by_id(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    assert await mongo_controller.get_order_by_id(ORDER_1.internal_id)

    assert not await mongo_controller.get_order_by_id(uuid4())


async def test_delete_order(mongo_controller, repositories):
    await create_strategy_with_orders(repositories)

    assert await mongo_controller.delete_order(ORDER_1)
    assert not await mongo_controller.delete_order(ORDER_1)

    assert not await mongo_controller.get_order_by_id(ORDER_1.internal_id)
