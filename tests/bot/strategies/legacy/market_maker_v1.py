from copy import deepcopy
from datetime import datetime
from decimal import Decimal

from pytest import fixture, mark, raises

from analyst.bot.exceptions import StrategyExit
from analyst.bot.strategies.market_maker import MarketMakerV1
from analyst.crypto.models import MarketStreamTicker, OutboundAccountBalance, OutboundAccountPosition
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
async def test_market_maker_creation(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal(0.004),
    )

    assert strategy.internal_order_id is None

    strategy.gatekeeping(order_manager)


@mark.skip
async def test_market_maker_creation_exception(order_manager):
    strategy = MarketMakerV1.create(
        symbol="FAKEBTC",
        amount=Decimal(0.004),
    )

    with raises(Exception, match="Pair FAKEBTC does not exist"):
        strategy.gatekeeping(order_manager)

    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal(1.5),
    )

    with raises(Exception, match="Insufficient funds"):
        strategy.gatekeeping(order_manager)


@mark.skip
async def test_market_maker_buy_and_sell_and_stop_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    assert strategy.internal_order_id

    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.internal_order_id == order.internal_id

    assert order.strategy_id == strategy.id
    assert order.side == "BUY"
    assert order.status == "NEW"

    filled_buy = await order_manager.fill_order(order, strategy)

    order = await strategy.process_order(filled_buy, order_manager)

    assert strategy.converted_amount == order.requested_quantity

    await strategy.pending_stop(order_manager)

    assert strategy.is_stopping
    assert strategy.internal_order_id == order.internal_id

    assert order.strategy_id == strategy.id
    assert order.side == "SELL"
    assert order.status == "NEW"

    filled_sell = await order_manager.fill_order(order, strategy)

    try:
        await strategy.process_order(filled_sell, order_manager)
    except StrategyExit:
        pass

    assert strategy.is_stopped
    assert strategy.internal_order_id is None
    assert strategy.converted_amount == Decimal()


@mark.skip
async def test_market_maker_buy_and_sell_and_continue_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    assert strategy.internal_order_id

    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.internal_order_id == order.internal_id

    assert order.strategy_id == strategy.id
    assert order.side == "BUY"
    assert order.status == "NEW"

    filled_buy = await order_manager.fill_order(order, strategy)

    order = await strategy.process_order(filled_buy, order_manager)

    assert strategy.converted_amount == order.requested_quantity

    assert order.strategy_id == strategy.id
    assert order.side == "SELL"
    assert order.status == "NEW"

    filled_sell = await order_manager.fill_order(order, strategy)

    order = await strategy.process_order(filled_sell, order_manager)

    assert strategy.internal_order_id == order.internal_id
    assert strategy.converted_amount == Decimal()

    assert order.strategy_id == strategy.id
    assert order.side == "BUY"
    assert order.status == "NEW"


@mark.skip
async def test_market_maker_price_going_down_flag_trigger_and_release_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    low_bid_quantity_ticker = MarketStreamTicker(
        symbol="AMPBTC",
        last_price=Decimal("0.00000030"),
        ask_price=Decimal("0.00000031"),
        ask_quantity=Decimal("1_000_000"),
        bid_price=Decimal("0.00000030"),
        bid_quantity=Decimal("50_000"),
        trades=500,
    )
    balanced_quantity_ticker = MarketStreamTicker(
        symbol="AMPBTC",
        last_price=Decimal("0.00000030"),
        ask_price=Decimal("0.00000031"),
        ask_quantity=Decimal("1_000_000"),
        bid_price=Decimal("0.00000030"),
        bid_quantity=Decimal("100_000"),
        trades=500,
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(low_bid_quantity_ticker, order_manager)

    assert not strategy.internal_order_id
    assert strategy.flags == MarketMakerV1.Flags.price_going_down

    await strategy.process_ticker_data(balanced_quantity_ticker, order_manager)

    assert strategy.internal_order_id
    assert strategy.flags == MarketMakerV1.Flags.no_flags

    order = order_manager.get_order(strategy.internal_order_id)
    order.executed_quantity = order.requested_quantity // 2

    updated_order = await order_manager.update_order(order)

    await strategy.process_ticker_data(low_bid_quantity_ticker, order_manager)

    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.converted_amount == Decimal("6666")

    assert order.side == "SELL"
    assert order.requested_quantity == updated_order.executed_quantity

    await strategy.process_ticker_data(balanced_quantity_ticker, order_manager)
    await strategy.process_ticker_data(low_bid_quantity_ticker, order_manager)

    order = await order_manager.fill_order(order_manager.get_order(strategy.internal_order_id))

    assert not await strategy.process_order(order, order_manager)
    assert not strategy.internal_order_id
    assert strategy.converted_amount == Decimal()

    assert not await strategy.process_ticker_data(low_bid_quantity_ticker, order_manager)
    assert not strategy.internal_order_id
    assert strategy.converted_amount == Decimal()

    await strategy.process_ticker_data(balanced_quantity_ticker, order_manager)
    assert strategy.internal_order_id


@mark.skip
async def test_market_maker_buy_context_and_price_goes_up_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.requested_quantity == Decimal("13333.0")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000031"),
            ask_price=Decimal("0.00000032"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000031"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price != order.price
    assert order.price == Decimal("0.00000031")
    assert order.requested_quantity == Decimal("12903.0")

    order.executed_quantity = order.requested_quantity // 4
    order = await order_manager.update_order(order)

    assert order.executed_quantity == Decimal("3225")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000032"),
            ask_price=Decimal("0.00000033"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000032"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.converted_amount == Decimal("3225")

    assert last_order.price != order.price
    assert order.price == Decimal("0.00000032")
    assert order.requested_quantity == Decimal("9375.0")


@mark.skip
async def test_market_maker_buy_context_and_price_goes_up_with_price_goes_down_flag_scenario(
    order_manager,
):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.price == Decimal("0.00000030")
    assert order.requested_quantity == Decimal("13333.0")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000031"),
            ask_price=Decimal("0.00000032"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000031"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price == order.price
    assert order.price == Decimal("0.00000030")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000032"),
            ask_price=Decimal("0.00000033"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000032"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price == order.price
    assert order.price == Decimal("0.00000030")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000032"),
            ask_price=Decimal("0.00000033"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000032"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price != order.price
    assert order.price == Decimal("0.00000032")


@mark.skip
async def test_market_maker_buy_context_and_price_goes_up_and_down_with_price_goes_down_flag_scenario(
    order_manager,
):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.price == Decimal("0.00000030")
    assert order.requested_quantity == Decimal("13333.0")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000031"),
            ask_price=Decimal("0.00000032"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000031"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price == order.price
    assert order.price == Decimal("0.00000030")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000029"),
            ask_price=Decimal("0.00000030"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000029"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price != order.price
    assert order.price == Decimal("0.00000029")


@mark.skip
async def test_market_maker_sell_context_and_price_goes_down_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    filled_buy = await order_manager.fill_order(order, strategy)

    order = await strategy.process_order(filled_buy, order_manager)

    assert strategy.converted_amount == Decimal("13333.0")

    assert order.side == "SELL"
    assert order.requested_quantity == Decimal("13333.0")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000029"),
            ask_price=Decimal("0.00000030"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000029"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert last_order.price != order.price
    assert order.price == Decimal("0.00000030")
    assert order.requested_quantity == Decimal("13333.0")

    order.executed_quantity = order.requested_quantity // 4
    order = await order_manager.update_order(order)

    assert strategy.converted_amount == Decimal("13333.0")

    assert order.executed_quantity == Decimal("3333")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000028"),
            ask_price=Decimal("0.00000029"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000028"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    last_order = order
    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.converted_amount == Decimal("10000.0")

    assert last_order.price != order.price
    assert order.side == "SELL"
    assert order.price == Decimal("0.00000029")
    assert order.requested_quantity == Decimal("10000.0")


@mark.skip
async def test_market_maker_buy_context_and_price_going_down_flag_raise_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.requested_quantity == Decimal("13333.0")

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    assert not strategy.internal_order_id

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_500_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.side == "BUY"
    assert order.requested_quantity == Decimal("13333.0")

    order.executed_quantity = Decimal("6666.0")
    order = await order_manager.update_order(order)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("50_000"),
            trades=500,
        ),
        order_manager,
    )

    order = order_manager.get_order(strategy.internal_order_id)

    assert strategy.converted_amount == Decimal("6666.0")

    assert order.side == "SELL"
    assert order.requested_quantity == Decimal("6666.0")


@mark.skip
async def test_market_maker_buy_context_and_stopping_issued_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("0.004"),
    )

    default_market_ticker = MarketStreamTicker(
        symbol="AMPBTC",
        last_price=Decimal("0.00000030"),
        ask_price=Decimal("0.00000031"),
        ask_quantity=Decimal("1_000_000"),
        bid_price=Decimal("0.00000030"),
        bid_quantity=Decimal("1_000_000"),
        trades=500,
    )

    await strategy.setup(order_manager)
    await strategy.process_ticker_data(default_market_ticker, order_manager)
    await strategy.pending_stop(order_manager)

    try:
        await strategy.process_ticker_data(default_market_ticker, order_manager)
    except StrategyExit:
        pass

    assert not strategy.internal_order_id


@mark.skip
async def test_market_maker_insufficient_fund_on_creation_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("1.2"),
    )

    await strategy.setup(order_manager)

    try:
        await strategy.process_ticker_data(
            MarketStreamTicker(
                symbol="AMPBTC",
                last_price=Decimal("0.00000030"),
                ask_price=Decimal("0.00000031"),
                ask_quantity=Decimal("1_000_000"),
                bid_price=Decimal("0.00000030"),
                bid_quantity=Decimal("1_000_000"),
                trades=500,
            ),
            order_manager,
        )
    except StrategyExit:
        pass

    assert strategy.is_stopped
    assert strategy.flags == MarketMakerV1.Flags.insufficient_fund


@mark.skip
async def test_market_maker_insufficient_fund_after_buy_sell_scenario(order_manager):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        amount=Decimal("1"),
    )

    await strategy.setup(order_manager)

    await strategy.process_ticker_data(
        MarketStreamTicker(
            symbol="AMPBTC",
            last_price=Decimal("0.00000030"),
            ask_price=Decimal("0.00000031"),
            ask_quantity=Decimal("1_000_000"),
            bid_price=Decimal("0.00000030"),
            bid_quantity=Decimal("1_000_000"),
            trades=500,
        ),
        order_manager,
    )

    assert strategy.internal_order_id

    order = order_manager.get_order(strategy.internal_order_id)

    assert order.side == "BUY"
    assert order.status == "NEW"

    filled_buy = await order_manager.fill_order(order, strategy)

    order = await strategy.process_order(filled_buy, order_manager)

    assert strategy.converted_amount == Decimal("3333333.0")

    assert order.side == "SELL"
    assert order.status == "NEW"

    filled_sell = await order_manager.fill_order(order, strategy)

    order_manager.update_account_with_live_data(
        OutboundAccountPosition(
            updated_at=datetime.now(),
            balances=[OutboundAccountBalance(coin="BTC", free=Decimal("0.9"), locked=Decimal())],
        )
    )

    try:
        assert not await strategy.process_order(filled_sell, order_manager)
    except StrategyExit:
        pass

    assert strategy.converted_amount == Decimal("0.0")
    assert strategy.is_stopped
    assert strategy.flags == MarketMakerV1.Flags.insufficient_fund
