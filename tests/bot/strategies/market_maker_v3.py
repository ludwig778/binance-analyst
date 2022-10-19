from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from freezegun import freeze_time
from pytest import fixture, mark, raises

from analyst.bot.exceptions import StrategyHalt
from analyst.bot.strategies.market_maker import MarketMakerV3
from analyst.crypto.exceptions import OrderWouldMatch
from tests.mocks.common import mock_account_info, mock_exchange_data_info, mock_pair_prices_info
from tests.mocks.order_manager import MockedOrderManager
from tests.utils import forge_stream_ticker


@fixture(scope="function", autouse=True)
async def setup_mocks(adapters, monkeypatch, order_manager):
    mock_account_info(adapters, monkeypatch)
    mock_exchange_data_info(adapters, monkeypatch)
    mock_pair_prices_info(adapters, monkeypatch)

    async def mock_get_updated_order(order):
        return deepcopy(order)

    monkeypatch.setattr(order_manager.controllers.binance, "get_updated_order", mock_get_updated_order)

    await order_manager.setup()


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


async def test_creation(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("1000"),
        cleanup_interval=timedelta(minutes=45),
        max_buy_orders=2,
        max_increase_step=6,
        max_increase_retain_delta=timedelta(days=1),
    )

    assert strategy.internal_buy_order_ids == set()
    assert strategy.internal_sell_order_ids == set()

    strategy.gatekeeping(order_manager)

    assert strategy.get_stream_names() == ["btcusdt@ticker"]

    assert strategy.to_str() == "market_maker:v3 on BTCUSDT"
    assert strategy.get_key() == "BTCUSDT:10:1000:False"
    assert strategy.flags == MarketMakerV3.Flags.no_flags


async def test_setup(order_manager, controllers):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("500"),
        max_buy_orders=3,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_000"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 3
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("15_000", "14_500", "14_000")])

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order = await order_manager.fill_order(highest_buy_order, strategy)

    await strategy.process_order(highest_buy_order, order_manager)
    await strategy.update_buy_side(order_manager, Decimal("14_500"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 3
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("14_500", "14_000", "13_500")])

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order = await order_manager.fill_order(highest_buy_order, strategy)

    await strategy.process_order(highest_buy_order, order_manager)
    await strategy.update_buy_side(order_manager, Decimal("14_000"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 3
    assert len(sell_orders) == 2
    assert set(sell_orders.keys()) == set([Decimal(p) for p in ("15_500", "15_000")])

    highest_buy_order = buy_orders.pop(max(buy_orders))

    await order_manager.fill_order(highest_buy_order, strategy)

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order.status = "PARTIALLY_FILLED"
    highest_buy_order.executed_quantity = highest_buy_order.requested_quantity / 3

    lowest_sell_order = sell_orders[min(sell_orders)][0]

    await order_manager.update_order(highest_buy_order, strategy)
    await order_manager.fill_order(lowest_sell_order, strategy)

    assert order_manager.orders

    order_manager.orders = {}

    await strategy.setup(order_manager)

    assert len(strategy.internal_buy_order_ids) == 2
    assert len(strategy.internal_sell_order_ids) == 1

    assert len(order_manager.orders) == 3
    assert (
        strategy.internal_buy_order_ids.intersection(set(order_manager.orders.keys()))
        == strategy.internal_buy_order_ids
    )
    assert (
        strategy.internal_sell_order_ids.intersection(set(order_manager.orders.keys()))
        == strategy.internal_sell_order_ids
    )

    await controllers.mongo.store_strategy(strategy)


async def test_creation_exception_gatekeeping_insufficient_funds(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("110"),
        interval=Decimal("1000"),
    )

    with raises(Exception, match="Insufficient funds"):
        strategy.gatekeeping(order_manager)


async def test_creation_exception_gatekeeping_interval_must_be_positive(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("-1000"),
    )

    with raises(Exception, match="Interval must be positive"):
        strategy.gatekeeping(order_manager)


async def test_creation_exception_gatekeeping_pair_does_not_exist(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCFAKE",
        quote_quantity=Decimal("10"),
        interval=Decimal("1000"),
    )

    with raises(Exception, match="Pair BTCFAKE does not exist"):
        strategy.gatekeeping(order_manager)


@mark.parametrize(
    "max_buy_orders,bid_price,interval,expected_prices",
    [
        (2, "15_000", "500", ["15_000", "14_500"]),
        (3, "15_123", "1_000", ["15_000", "14_000", "13_000"]),
        (5, "15_000", "200", ["15_000", "14_800", "14_600", "14_400", "14_200"]),
    ],
)
async def test_update_buy_side(order_manager, max_buy_orders, bid_price, interval, expected_prices):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal(interval),
        max_buy_orders=max_buy_orders,
    )

    await strategy.update_buy_side(order_manager, Decimal(bid_price))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert set(buy_orders.keys()) == set([Decimal(p) for p in expected_prices])


async def test_update_buy_side_exception_insufficient_fund(order_manager, monkeypatch):
    quote_quantity = Decimal("33")

    async def mocked_create_order(**kwargs):
        order = await MockedOrderManager._create_order(order_manager, **kwargs)

        order_manager.account["USDT"].quantity -= quote_quantity

        return order

    monkeypatch.setattr(order_manager, "_create_order", mocked_create_order)

    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=quote_quantity,
        interval=Decimal("500"),
        max_buy_orders=4,
    )

    with raises(StrategyHalt):
        await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 3


async def test_max_buy_orders_exception_order_would_match(order_manager, monkeypatch):
    async def mocked_create_order(**kwargs):
        if kwargs["side"] == "BUY" and Decimal(kwargs["price"]) >= Decimal("14_800"):
            raise OrderWouldMatch()

        return await MockedOrderManager._create_order(order_manager, **kwargs)

    monkeypatch.setattr(order_manager, "_create_order", mocked_create_order)

    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("500"),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 4
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("14_500", "14_000", "13_500", "13_000")])


async def test_max_buy_orders_buy_and_sell_complete_flow(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("500"),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 4
    assert len(sell_orders) == 0
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("15_000", "14_500", "14_000", "13_500")])

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order = await order_manager.fill_order(highest_buy_order, strategy)

    await strategy.process_order(highest_buy_order, order_manager)
    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 4
    assert len(sell_orders) == 1
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("14_500", "14_000", "13_500", "13_000")])

    self_order = sell_orders[Decimal("15_500")][0]
    self_order = await order_manager.fill_order(self_order, strategy)

    await strategy.process_order(self_order, order_manager)
    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 5
    assert len(sell_orders) == 0
    assert set(buy_orders.keys()) == set(
        [Decimal(p) for p in ("15_000", "14_500", "14_000", "13_500", "13_000")]
    )


async def test_max_buy_orders_sell_back_canceled_orders_on_quote_price_change(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("500"),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    for order in buy_orders.values():
        order.status = "PARTIALLY_FILLED"
        order.executed_quantity = order.requested_quantity / 3
        order = await order_manager.update_order(order, strategy)

        await strategy.process_order(order, order_manager)

    strategy.quote_quantity = Decimal("15")
    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 4
    assert len(sell_orders) == 1
    assert set(sell_orders.keys()) == set([Decimal("15_500")])

    assert sell_orders[Decimal("15_500")][0].requested_quantity == Decimal("0.00095")


@mark.parametrize(
    "interval,would_match_limit,expected_sell_price",
    [
        ("200", "15_000", "15_200"),
        ("300", "15_000", "15_300"),
        ("300", "15_400", "15_600"),
        ("300", "17_000", "17_100"),
    ],
)
async def test_sell_back(order_manager, monkeypatch, interval, would_match_limit, expected_sell_price):
    async def mocked_create_order(**kwargs):
        if kwargs["side"] == "SELL" and Decimal(kwargs["price"]) <= Decimal(would_match_limit):
            raise OrderWouldMatch()

        return await MockedOrderManager._create_order(order_manager, **kwargs)

    monkeypatch.setattr(order_manager, "_create_order", mocked_create_order)

    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal(interval),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    assert len(strategy.internal_buy_order_ids) == 4

    buy_orders = strategy.get_buy_orders(order_manager)
    top_buy_order_prices = list(sorted(buy_orders.keys(), reverse=True))[:2]

    for price in top_buy_order_prices:
        order = buy_orders[price]
        order.executed_quantity = order.requested_quantity / 2

        await order_manager.update_order(order, strategy)

    await strategy.update_buy_side(order_manager, Decimal("14_980"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert set(sell_orders.keys()) == set([Decimal(expected_sell_price)])


async def test_update_buy_side_exception_bid_price_near_zero(order_manager, monkeypatch):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("1_000"),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("565"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 0


async def test_update_buy_side_exception_would_match_over_threshold(order_manager, monkeypatch):
    async def mocked_create_order(**kwargs):
        if kwargs["side"] == "BUY":
            raise OrderWouldMatch()

        return await MockedOrderManager._create_order(order_manager, **kwargs)

    monkeypatch.setattr(order_manager, "_create_order", mocked_create_order)

    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=4,
    )

    with raises(StrategyHalt):
        await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 0


async def test_sell_back_exception_would_match_over_threshold(order_manager, monkeypatch):
    async def mocked_create_order(**kwargs):
        if kwargs["side"] == "SELL":
            raise OrderWouldMatch()

        return await MockedOrderManager._create_order(order_manager, **kwargs)

    monkeypatch.setattr(order_manager, "_create_order", mocked_create_order)

    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=4,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order = await order_manager.fill_order(highest_buy_order, strategy)

    with raises(StrategyHalt):
        await strategy.process_order(highest_buy_order, order_manager)

    assert len(buy_orders) == 4
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("15_200", "15_100", "15_000", "14_900")])


async def test_terminate(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=3,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 3

    assert not await strategy.terminate(order_manager)

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 0
    assert len(sell_orders) == 0


async def test_terminate_with_sell_back(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=3,
    )

    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    highest_buy_order = buy_orders[max(buy_orders)]
    highest_buy_order.status = "PARTIALLY_FILLED"
    highest_buy_order.executed_quantity = highest_buy_order.requested_quantity / 3

    highest_buy_order = await order_manager.update_order(highest_buy_order, strategy)

    sell_order = await strategy.terminate(order_manager)

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 0
    assert len(sell_orders) == 0

    assert sell_order.requested_quantity == Decimal("0.00022")


async def test_safe_stop_check(order_manager):
    symbol = "BTCUSDT"

    strategy = MarketMakerV3.create(
        symbol=symbol,
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=3,
        max_increase_step=10,
        max_increase_retain_delta=timedelta(hours=1),
    )

    for increment in range(0, 1000, 100):
        await strategy.process_ticker_data(
            forge_stream_ticker(
                symbol=symbol,
                bid_price=Decimal("15_000") + increment,
                ask_price=Decimal("15_010") + increment,
            ),
            order_manager,
        )

    assert len(strategy._last_price_timestamps) == 10

    with freeze_time(strategy._last_update + timedelta(hours=1, seconds=1)):
        await strategy.process_ticker_data(
            forge_stream_ticker(
                symbol=symbol,
                bid_price=Decimal("16_000"),
                ask_price=Decimal("16_010"),
            ),
            order_manager,
        )

        assert len(strategy._last_price_timestamps) == 1

        for increment in range(100, 1000, 100):
            await strategy.process_ticker_data(
                forge_stream_ticker(
                    symbol=symbol,
                    bid_price=Decimal("16_000") + increment,
                    ask_price=Decimal("16_010") + increment,
                ),
                order_manager,
            )

        with raises(StrategyHalt):
            await strategy.process_ticker_data(
                forge_stream_ticker(
                    symbol=symbol,
                    bid_price=Decimal("17_000") + increment,
                    ask_price=Decimal("17_010") + increment,
                ),
                order_manager,
            )


async def test_safe_stop_check_with_disable_max_increase_step_check(order_manager):
    symbol = "BTCUSDT"

    strategy = MarketMakerV3.create(
        symbol=symbol,
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=3,
        max_increase_step=0,
        max_increase_retain_delta=timedelta(hours=1),
    )

    await strategy.process_ticker_data(
        forge_stream_ticker(
            symbol=symbol,
            bid_price=Decimal("15_000"),
            ask_price=Decimal("15_010"),
        ),
        order_manager,
    )

    assert len(strategy._last_price_timestamps) == 0


async def test_cleanup_buy_side(order_manager):
    strategy = MarketMakerV3.create(
        symbol="BTCUSDT",
        quote_quantity=Decimal("10"),
        interval=Decimal("100"),
        max_buy_orders=3,
    )

    await strategy.cleanup_buy_side(order_manager, Decimal("15_237"))
    await strategy.update_buy_side(order_manager, Decimal("15_237"))

    buy_orders = strategy.get_buy_orders(order_manager)

    assert len(buy_orders) == 3
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("15_200", "15_100", "15_000")])

    await strategy.update_buy_side(order_manager, Decimal("15_537"))

    buy_orders = strategy.get_buy_orders(order_manager)

    sorted_buy_orders = list(sorted(buy_orders.values(), key=lambda x: x.price, reverse=True))

    for order in sorted_buy_orders[strategy.max_buy_orders:]:
        order.status = "PARTIALLY_FILLED"
        order.executed_quantity = order.requested_quantity / 3
        order = await order_manager.update_order(order, strategy)

        await strategy.process_order(order, order_manager)

    assert len(buy_orders) == 6
    assert set(buy_orders.keys()) == set(
        [Decimal(p) for p in ("15_500", "15_400", "15_300", "15_200", "15_100", "15_000")]
    )

    await strategy.cleanup_buy_side(order_manager, Decimal("15_537"))

    buy_orders = strategy.get_buy_orders(order_manager)
    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(buy_orders) == 3
    assert len(sell_orders) == 1
    assert set(buy_orders.keys()) == set([Decimal(p) for p in ("15_500", "15_400", "15_300")])
    assert set(sell_orders.keys()) == set([Decimal("15_600")])
