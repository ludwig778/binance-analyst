from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pprint import pprint

from freezegun import freeze_time
from pytest import fixture, mark, raises

from analyst.bot.exceptions import StrategyExit
from analyst.bot.strategies.market_maker import MarketMakerV2
from analyst.crypto.models import MarketStreamTicker
from tests.mocks.common import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


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


@mark.skip
async def test_market_maker_creation(order_manager, controllers, repositories):
    strategy = MarketMakerV2.create(
        symbol="AMPBTC",
        quote_quantity=Decimal("0.004"),
        max_buy_orders=2,
        max_increase_step=6,
        max_increase_retain_delta=timedelta(days=1),
    )

    assert strategy.internal_buy_order_ids == set()
    assert strategy.internal_sell_order_ids == set()

    await controllers.mongo.store_strategy(strategy)

    print("\n\n")

    def get_default_stream_ticker(ask_price, bid_price):
        return MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal(ask_price),
            ask_price=Decimal(ask_price),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal(bid_price),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        )

    def show():
        pprint(
            [
                (order.price, str(order.internal_id)[:8], order.requested_quantity, order.side)
                for order in order_manager.orders.values()
            ]
        )

    await strategy.process_ticker_data(
        get_default_stream_ticker("0.00000031", "0.00000030"), order_manager
    )

    assert len(strategy.internal_buy_order_ids) == 2
    assert len(strategy.internal_sell_order_ids) == 0

    await strategy.process_ticker_data(
        get_default_stream_ticker("0.00000033", "0.00000032"), order_manager
    )

    assert len(strategy.internal_buy_order_ids) == 4
    assert len(strategy.internal_sell_order_ids) == 0

    await strategy.process_ticker_data(
        get_default_stream_ticker("0.00000032", "0.00000031"), order_manager
    )

    assert len(strategy.internal_buy_order_ids) == 3
    assert len(strategy.internal_sell_order_ids) == 0

    assert len(order_manager.orders.values()) == 3

    last_order = list(order_manager.orders.values())[-1]

    assert last_order.id == 4

    # pprint(last_order.dict())

    filled_buy = await order_manager.fill_order(last_order, strategy)
    await strategy.process_order(filled_buy, order_manager)

    last_order = list(order_manager.orders.values())[-1]

    assert len(strategy.internal_buy_order_ids) == 2
    assert len(strategy.internal_sell_order_ids) == 1
    assert last_order.id == 5
    assert last_order.side == "SELL"

    show()

    await strategy.process_ticker_data(
        get_default_stream_ticker("0.00000031", "0.00000030"), order_manager
    )

    show()

    filled_sell = await order_manager.fill_order(last_order, strategy)
    await strategy.process_order(filled_sell, order_manager)

    show()

    """
    filled_sell = await order_manager.fill_order(next_to_last_order, strategy)
    await strategy.process_order(filled_sell, order_manager)
    """
    strategy.quote_quantity = Decimal("0.005")

    order = list(order_manager.orders.values())[0]
    order.executed_quantity = (order.requested_quantity // 3) * 2
    await order_manager.update_order(order, strategy)
    order = list(order_manager.orders.values())[1]
    order.executed_quantity = order.requested_quantity // 2
    await order_manager.update_order(order, strategy)

    show()

    await strategy.process_ticker_data(
        get_default_stream_ticker("0.00000031", "0.00000030"), order_manager
    )

    show()

    await controllers.mongo.store_strategy(strategy)

    sell_orders = strategy.get_sell_orders(order_manager)

    assert len(sell_orders[Decimal("0.00000031")]) == 1

    for stream_ticker in [
        get_default_stream_ticker("0.00000031", "0.00000030"),
        get_default_stream_ticker("0.00000032", "0.00000031"),
        get_default_stream_ticker("0.00000033", "0.00000032"),
        get_default_stream_ticker("0.00000034", "0.00000033"),
        get_default_stream_ticker("0.00000035", "0.00000034"),
        get_default_stream_ticker("0.00000036", "0.00000035"),
    ]:
        await strategy.process_ticker_data(stream_ticker, order_manager)

    assert len(strategy.internal_buy_order_ids) == 7
    assert len(strategy.internal_sell_order_ids) == 1

    with raises(StrategyExit):
        await strategy.process_ticker_data(
            get_default_stream_ticker("0.00000037", "0.00000036"), order_manager
        )

    last_price_timestamp = max(strategy._last_price_timestamps.values())
    with freeze_time(last_price_timestamp + timedelta(days=1, seconds=1)):
        await strategy.process_ticker_data(
            get_default_stream_ticker("0.00000037", "0.00000036"), order_manager
        )

        assert len(strategy._last_price_timestamps) == 1
        assert list(strategy._last_price_timestamps.keys())[0] == Decimal("0.00000036")

    await strategy.terminate(order_manager)

    assert len(strategy.internal_buy_order_ids) == 0
    assert len(strategy.internal_sell_order_ids) == 1

    """
    strat = (await repositories.strategies.list())[0]

    pprint(strat.dict())
    pprint(strat.internal_buy_order_ids)
    pprint(strat.internal_sell_order_ids)
    """
