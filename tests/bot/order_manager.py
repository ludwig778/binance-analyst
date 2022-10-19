from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pytest import fixture, raises

from analyst.bot.order_manager import PairSide, Side
from analyst.crypto.exceptions import PriceMustBeSetOnMarketMakingOrder
from analyst.crypto.models import CoinAmount, Order, OutboundAccountBalance, OutboundAccountPosition
from tests.fixtures.orders import ORDER_1
from tests.mocks.common import (
    mock_account_info,
    mock_coroutine_return,
    mock_exchange_data_info,
    mock_pair_prices_info,
)


@fixture(scope="function", autouse=True)
async def setup_mocks(adapters, monkeypatch, order_manager):
    mock_account_info(adapters, monkeypatch)
    mock_exchange_data_info(adapters, monkeypatch)
    mock_pair_prices_info(adapters, monkeypatch)

    await order_manager.setup()


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


async def test_setup(order_manager):
    assert order_manager.account
    assert order_manager.pairs


async def test_get_pair(order_manager):
    assert order_manager.get_pair("BTCUSDT")

    with raises(KeyError):
        order_manager.get_pair("FAKECOIN")


async def test_update_account_with_live_data(order_manager):
    outbound_account_position = OutboundAccountPosition(
        updated_at=datetime.now(),
        balances=[
            OutboundAccountBalance(coin="BNB", free=Decimal("6.78"), locked=Decimal(0)),
            OutboundAccountBalance(coin="AMP", free=Decimal("20000"), locked=Decimal(0)),
            OutboundAccountBalance(a="BTC", f=Decimal("1.3"), l=Decimal(0)),
        ],
    )

    order_manager.update_account_with_live_data(outbound_account_position)

    assert order_manager.account["BNB"] == CoinAmount(coin="BNB", quantity=Decimal("6.78"))
    assert order_manager.account["BTC"] == CoinAmount(coin="BTC", quantity=Decimal("1.3"))
    assert order_manager.account["AMP"] == CoinAmount(coin="AMP", quantity=Decimal("20000"))


async def test_get_account_quantity(order_manager):
    btc_usdt = order_manager.get_pair("BTCUSDT")
    bnb_btc = order_manager.get_pair("BNBBTC")

    assert order_manager.get_account_quantity(btc_usdt, PairSide.base) == Decimal(1)
    assert order_manager.get_account_quantity(bnb_btc, PairSide.base) == Decimal(10)

    assert order_manager.get_account_quantity(btc_usdt, PairSide.quote) == Decimal(100)
    assert order_manager.get_account_quantity(bnb_btc, PairSide.quote) == Decimal(1)


async def test_has_sufficient_quantity(order_manager):
    btc_usdt = order_manager.get_pair("BTCUSDT")
    link_bnb = order_manager.get_pair("LINKBNB")

    assert order_manager.has_sufficient_quantity(btc_usdt, Decimal("1.0"), PairSide.base)
    assert not order_manager.has_sufficient_quantity(btc_usdt, Decimal("1.5"), PairSide.base)

    assert order_manager.has_sufficient_quantity(link_bnb, Decimal("9"), PairSide.quote)
    assert not order_manager.has_sufficient_quantity(link_bnb, Decimal("15"), PairSide.quote)


async def test_truncate_base_quantity(order_manager):
    uni_btc = order_manager.get_pair("UNIBTC")
    doge_btc = order_manager.get_pair("DOGEBTC")

    quantity = Decimal("1234.5678")

    assert order_manager.truncate_base_quantity(uni_btc, quantity) == Decimal("1234.56")
    assert order_manager.truncate_base_quantity(uni_btc, quantity, ceil=True) == Decimal("1234.57")

    assert order_manager.truncate_base_quantity(doge_btc, quantity) == Decimal("1234")
    assert order_manager.truncate_base_quantity(doge_btc, quantity, ceil=True) == Decimal("1235")


async def test_get_fee_optimized_quantity_available(order_manager, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_account_info",
        mock_coroutine_return({"balances": [{"asset": "AMP", "free": "10000", "locked": "0.0"}]}),
    )

    max_base_quantity = await order_manager.get_fee_optimized_quantity_available(
        Order.create(
            id=1,
            symbol="AMPBTC",
            status="NEW",
            type="LIMIT_MAKER",
            side="BUY",
            price=Decimal("0.00000029"),
            requested_quantity=Decimal("10000"),
            executed_quantity=Decimal("10000"),
        )
    )
    assert max_base_quantity == Decimal("10000")

    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_account_info",
        mock_coroutine_return({"balances": [{"asset": "AMP", "free": "9994.5", "locked": "0.0"}]}),
    )

    max_base_quantity = await order_manager.get_fee_optimized_quantity_available(
        Order.create(
            id=1,
            symbol="AMPBTC",
            status="NEW",
            type="LIMIT_MAKER",
            side="BUY",
            price=Decimal("0.00000029"),
            requested_quantity=Decimal("10000"),
            executed_quantity=Decimal("10000"),
        )
    )
    assert max_base_quantity == Decimal("9994")


async def test_convert_quantity(order_manager):
    uni_btc = order_manager.get_pair("UNIBTC")
    doge_btc = order_manager.get_pair("DOGEBTC")

    assert order_manager.convert_quantity(Decimal("1"), uni_btc.ask_price, to=PairSide.base) == Decimal(
        "3143.665513989311537252436341"
    )
    assert order_manager.convert_quantity(Decimal("1"), uni_btc.bid_price, to=PairSide.base) == Decimal(
        "3144.654088050314465408805031"
    )

    assert order_manager.convert_quantity(Decimal("1"), doge_btc.ask_price, to=PairSide.base) == Decimal(
        "318471.3375796178343949044586"
    )
    assert order_manager.convert_quantity(Decimal("1"), doge_btc.bid_price, to=PairSide.base) == Decimal(
        "319488.8178913738019169329073"
    )

    assert order_manager.convert_quantity(
        Decimal("5000"), uni_btc.bid_price, to=PairSide.quote
    ) == Decimal("1.59000000")
    assert order_manager.convert_quantity(
        Decimal("5000"), uni_btc.ask_price, to=PairSide.quote
    ) == Decimal("1.59050000")

    assert order_manager.convert_quantity(
        Decimal("100000"), doge_btc.bid_price, to=PairSide.quote
    ) == Decimal("0.31300000")
    assert order_manager.convert_quantity(
        Decimal("100000"), doge_btc.ask_price, to=PairSide.quote
    ) == Decimal("0.31400000")


async def test_get_order(order_manager):
    order = await order_manager.sell_all_market("AMPBTC")

    assert order == order_manager.get_order(order.internal_id)
    assert order_manager.get_order(uuid4()) is None


async def test_setup_order(order_manager, controllers, monkeypatch):
    async def mock_get_updated_order(order):
        return deepcopy(order)

    monkeypatch.setattr(order_manager.controllers.binance, "get_updated_order", mock_get_updated_order)

    order = await controllers.mongo.store_order(ORDER_1)

    assert order == await order_manager.setup_order(order.internal_id)
    assert order_manager.get_order(order.internal_id) == order


async def test_create_order_buy_maker(order_manager):
    order = await order_manager.create_order(
        symbol="AMPBTC",
        side=Side.buy,
        price=Decimal("0.00000028"),
        quantity=Decimal("1000"),
        market_making=True,
    )

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="NEW",
        type="LIMIT_MAKER",
        side="BUY",
        price=Decimal("2.8E-7"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("0.0"),
        requested_quantity=Decimal("1000"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_create_order_sell_maker(order_manager):
    order = await order_manager.create_order(
        symbol="AMPBTC",
        side=Side.sell,
        price=Decimal("0.00000029"),
        quantity=Decimal("1500"),
        market_making=True,
    )

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="NEW",
        type="LIMIT_MAKER",
        side="SELL",
        price=Decimal("2.9E-7"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("0.0"),
        requested_quantity=Decimal("1500"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_create_order_buy_market(order_manager):
    order = await order_manager.create_order(
        symbol="AMPBTC",
        side=Side.buy,
        quantity=Decimal("2000"),
    )

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="FILLED",
        type="MARKET",
        side="BUY",
        price=Decimal("0.0"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("2000"),
        requested_quantity=Decimal("2000"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_create_order_sell_market(order_manager):
    order = await order_manager.create_order(
        symbol="AMPBTC",
        side=Side.sell,
        quantity=Decimal("2500"),
    )

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="FILLED",
        type="MARKET",
        side="SELL",
        price=Decimal("0.0"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("2500"),
        requested_quantity=Decimal("2500"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_create_order_exception(order_manager):
    with raises(PriceMustBeSetOnMarketMakingOrder):
        await order_manager.create_order(
            symbol="AMPBTC", side=Side.buy, quantity=Decimal("1000"), market_making=True
        )


async def test_sell_all_maker(order_manager):
    order = await order_manager.sell_all_maker("AMPBTC", Decimal("0.00000029"))

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="NEW",
        type="LIMIT_MAKER",
        side="SELL",
        price=Decimal("2.9E-7"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("0.0"),
        requested_quantity=Decimal("2000.0"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_sell_all_market(order_manager):
    order = await order_manager.sell_all_market("AMPBTC")

    assert order == Order(
        id=1,
        symbol="AMPBTC",
        status="FILLED",
        type="MARKET",
        side="SELL",
        price=Decimal("0.0"),
        stop_price=Decimal("0.0"),
        time_in_force="GTC",
        executed_quantity=Decimal("2000.0"),
        requested_quantity=Decimal("2000.0"),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=None,
        internal_id=order.internal_id,
    )


async def test_update_order(order_manager, controllers):
    order = await order_manager.sell_all_maker("AMPBTC", Decimal("0.00000029"))

    order.executed_quantity = order.requested_quantity / 2

    await order_manager.update_order(order)

    updated = (await controllers.mongo.get_orders(id=order.id, symbol=order.symbol))[0]

    assert updated.executed_quantity == updated.requested_quantity / 2


async def test_cancel_order(order_manager, controllers):
    order = await order_manager.sell_all_market("AMPBTC")

    await order_manager.cancel_order(order)

    cancelled = (await controllers.mongo.get_orders(id=order.id, symbol=order.symbol))[0]

    assert cancelled.status == "CANCELLED"


async def test_fill_order(order_manager, controllers):
    order = await order_manager.sell_all_maker("AMPBTC", Decimal("0.00000029"))

    await order_manager.fill_order(order)

    filled = (await controllers.mongo.get_orders(id=order.id, symbol=order.symbol))[0]

    assert filled.status == "FILLED"
    assert filled.executed_quantity == filled.requested_quantity


async def test_get_updated_orders(order_manager, monkeypatch):
    async def mock_get_updated_order(order):
        order = deepcopy(order)
        order.status = "CANCELLED"

        return order

    monkeypatch.setattr(order_manager.controllers.binance, "get_updated_order", mock_get_updated_order)

    order = await order_manager.create_order(
        symbol="AMPBTC", side=Side.buy, price=Decimal("0.00000028"), quantity=Decimal("3000")
    )

    order = deepcopy(order)
    order.status = "CANCELLED"

    assert await order_manager.get_updated_orders() == [order]
