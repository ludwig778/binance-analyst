from copy import deepcopy
from uuid import uuid4

from pytest import fixture, raises

from analyst.repositories.order import NoOrder, OrderAlreadyExist, OrderDoesNotExist
from tests.fixtures.orders import ORDER_1, ORDER_1_UPDATED, ORDER_2

STRATEGY_ID = uuid4()
STRATEGY_ID2 = uuid4()

ORDER_2 = deepcopy(ORDER_2)
ORDER_2.strategy_id = STRATEGY_ID
ORDER_1_UPDATED = deepcopy(ORDER_1_UPDATED)
ORDER_1_UPDATED.strategy_id = STRATEGY_ID2


@fixture(scope="function")
async def repositories(repositories):
    await repositories.orders.delete_all()

    yield repositories

    await repositories.orders.delete_all()


async def test_create(repositories):
    await repositories.orders.create(ORDER_1)

    order = await repositories.orders.get(symbol=ORDER_1.symbol, order_id=ORDER_1.id)

    assert ORDER_1.dict() == order.dict()


async def test_create_exception(repositories):
    await repositories.orders.create(ORDER_1)

    with raises(OrderAlreadyExist, match="Order 1 => ETHBTC already exists"):
        order = deepcopy(ORDER_1)
        order.internal_id = None

        await repositories.orders.create(order)

    with raises(OrderAlreadyExist, match=f"Order internal_id={ORDER_1.internal_id} already exists"):
        order = deepcopy(ORDER_1)
        order.id += 1

        await repositories.orders.create(order)


async def test_get(repositories):
    await repositories.orders.create(ORDER_1)

    retrieved = await repositories.orders.get(symbol=ORDER_1.symbol, order_id=ORDER_1.id)

    assert retrieved.dict() == ORDER_1.dict()


async def test_get_exception(repositories):
    with raises(OrderDoesNotExist, match="Order 1 => ETHBTC doesn't exists"):
        await repositories.orders.get(symbol=ORDER_1.symbol, order_id=ORDER_1.id)


async def test_get_by_id(repositories):
    await repositories.orders.create(ORDER_1)

    retrieved = await repositories.orders.get_by_id(internal_id=ORDER_1.internal_id)

    assert retrieved.dict() == ORDER_1.dict()


async def test_get_by_id_exception(repositories):
    with raises(OrderDoesNotExist, match=f"Order internal_id={ORDER_1.internal_id} doesn't exists"):
        await repositories.orders.get_by_id(internal_id=ORDER_1.internal_id)


async def test_list(repositories):
    orders = await repositories.orders.list(symbol="ETHBTC")

    assert orders == []

    await repositories.orders.create(ORDER_1)
    await repositories.orders.create(ORDER_2)

    orders = await repositories.orders.list(symbol="ETHBTC")

    assert len(orders) == 2

    orders = await repositories.orders.list(symbol="ETHBTC", limit=1)

    assert len(orders) == 1

    orders = await repositories.orders.list(strategy_id=STRATEGY_ID)

    assert len(orders) == 1

    orders = await repositories.orders.list(type={"$in": ["MARKET", "LIMIT_MAKER"]})

    assert len(orders) == 2


async def test_get_latest(repositories):
    await repositories.orders.create(ORDER_1)
    await repositories.orders.create(ORDER_2)

    order = await repositories.orders.get_latest(symbol="ETHBTC")

    assert order == ORDER_2


async def test_get_latest_exception(repositories):
    with raises(NoOrder, match="No orders for ETHBTC"):
        await repositories.orders.get_latest(symbol="ETHBTC")


async def test_update(repositories):
    await repositories.orders.create(ORDER_1)

    order = await repositories.orders.update(ORDER_1_UPDATED)

    assert order == ORDER_1_UPDATED


async def test_update_exception(repositories):
    with raises(
        OrderDoesNotExist, match=f"Order internal_id={ORDER_1_UPDATED.internal_id} doesn't exists"
    ):
        await repositories.orders.update(ORDER_1_UPDATED)


async def test_delete(repositories):
    order = await repositories.orders.create(ORDER_1)

    assert await repositories.orders.delete(order) is True


async def test_delete_exception(repositories):
    with raises(OrderDoesNotExist, match=f"Order internal_id={ORDER_1.internal_id} doesn't exists"):
        await repositories.orders.delete(ORDER_1)


async def test_delete_all(repositories):
    await repositories.orders.create(ORDER_1)
    await repositories.orders.create(ORDER_2)

    orders = await repositories.orders.list(symbol="ETHBTC")

    assert len(orders) == 2

    await repositories.orders.delete_all()

    orders = await repositories.orders.list(symbol="ETHBTC")

    assert orders == []
