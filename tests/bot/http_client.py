from decimal import Decimal

from pytest import fixture

from analyst.bot.bot import Runner
from analyst.bot.http_client import BotHttpClient
from analyst.bot.http_server import BotHttpServer
from analyst.bot.strategies.base import StrategyState
from analyst.bot.strategies.market_maker import MarketMakerV1
from analyst.crypto.models import Order
from tests.mocks.common import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


@fixture(scope="function")
async def bot(controllers, order_manager):
    return Runner(controllers=controllers, order_manager=order_manager)


@fixture(scope="function")
async def strategies():
    return [
        MarketMakerV1.create(symbol="AMPBTC", quote_quantity=Decimal(".002")),
        MarketMakerV1.create(
            symbol="QLCBTC", quote_quantity=Decimal(".004"), state=StrategyState.stopped
        ),
        MarketMakerV1.create(
            symbol="AMPBTC", quote_quantity=Decimal(".003"), state=StrategyState.stopping
        ),
        MarketMakerV1.create(
            symbol="QLCBTC",
            quote_quantity=Decimal(".003"),
            state=StrategyState.running,
            flags=MarketMakerV1.Flags.price_going_down,
        ),
    ]


@fixture(scope="function")
async def orders(strategies):
    return [
        Order.create(
            id=1,
            symbol="AMPBTC",
            status="FILLED",
            type="LIMIT_MAKER",
            side="BUY",
            price=Decimal("0.00000031"),
            requested_quantity=Decimal(2000),
            executed_quantity=Decimal(2000),
            strategy_id=strategies[0].id,
        ),
        Order.create(
            id=2,
            symbol="AMPBTC",
            status="FILLED",
            type="LIMIT_MAKER",
            side="SELL",
            price=Decimal("0.00000032"),
            requested_quantity=Decimal(2000),
            executed_quantity=Decimal(2000),
            strategy_id=strategies[0].id,
        ),
        Order.create(
            id=3,
            symbol="AMPBTC",
            status="FILLED",
            type="LIMIT_MAKER",
            side="SELL",
            price=Decimal("0.00000032"),
            requested_quantity=Decimal(2000),
            executed_quantity=Decimal(2000),
            strategy_id=strategies[0].id,
        ),
    ]


@fixture(scope="function", autouse=True)
async def setup_environment(
    settings, controllers, bot, order_manager, strategies, orders, adapters, monkeypatch
):
    mock_account_info(adapters, monkeypatch)
    mock_exchange_data_info(adapters, monkeypatch)
    mock_pair_prices_info(adapters, monkeypatch)

    async def mocked_send(*args, **kwargs):
        pass

    monkeypatch.setattr(adapters.binance_market_websocket, "send", mocked_send)

    await order_manager.setup()

    for strategy in strategies:
        await controllers.mongo.store_strategy(strategy)

    for order in orders:
        await controllers.mongo.store_order(order)

    await bot.setup()

    http_server = BotHttpServer(settings=settings.bot, bot=bot, controllers=controllers)

    await http_server.run()

    yield

    await http_server.stop()


@fixture(scope="function")
async def http_client(settings):
    return BotHttpClient(settings=settings.bot)


async def test_bot_http_client_ping(http_client):
    assert await http_client.ping() == {"status": "pong"}


async def test_bot_http_client_login(http_client):
    assert not http_client._token

    await http_client.login()

    assert http_client._token


async def test_bot_http_client_get_running_strategies(http_client, strategies):
    running_strategies = await http_client.get_running_strategies()

    running_strategies_items = list(running_strategies.items())

    assert running_strategies_items[0][0].dict() == strategies[0].dict()
    assert running_strategies_items[2][0].dict() == strategies[3].dict()

    orders = list(running_strategies.values())[0]

    assert len(orders) == 3


async def test_bot_http_client_add_strategy(http_client, adapters):
    assert adapters.binance_market_websocket.subscriptions == set()

    response = await http_client.add_strategy(
        "market_maker", "v1", {"quote_quantity": 1, "symbol": "AMPBTC"}
    )

    assert response == {"status": "ok"}
    assert adapters.binance_market_websocket.subscriptions == {"ampbtc@ticker"}

    response = await http_client.add_strategy("market_maker", "v1", {"quote_quantity": "nope"})

    assert response == {"status": "nok", "message": "[<class 'decimal.ConversionSyntax'>]"}

    response = await http_client.add_strategy("blank", "v0", {})

    assert response == {"status": "nok", "message": "Strategy blank:v0 does not exists"}

    response = await http_client.add_strategy(
        "market_maker", "v1", {"quote_quantity": 1, "symbol": "LINKBTC"}
    )

    assert response == {"status": "ok"}
    assert adapters.binance_market_websocket.subscriptions == {"ampbtc@ticker", "linkbtc@ticker"}


async def test_bot_http_client_stop_strategy(http_client, strategies):
    response = await http_client.stop_strategy(strategies[0])

    assert response == {"status": "ok"}

    response = await http_client.stop_strategy(strategies[0])

    assert response == {"status": "ok", "message": "Nothing to do, state is stopping"}

    response = await http_client.stop_strategy(strategies[1])

    assert response == {"status": "nok", "message": "Could not find strategy"}


async def test_bot_http_client_remove_strategy(http_client, strategies):
    response = await http_client.remove_strategy(strategies[0])

    assert response == {"status": "ok"}

    response = await http_client.remove_strategy(strategies[1])

    assert response == {"status": "nok", "message": "Could not find strategy"}


async def test_bot_http_client_add_and_remove_cycle(http_client, adapters):
    assert adapters.binance_market_websocket.subscriptions == set()

    response = await http_client.add_strategy(
        "market_maker", "v1", {"quote_quantity": 1, "symbol": "AMPBTC"}
    )

    assert adapters.binance_market_websocket.subscriptions == {"ampbtc@ticker"}
    assert response == {"status": "ok"}

    strategies = await http_client.get_running_strategies()
    strategies = list(strategies.items())

    assert len(strategies) == 4

    response = await http_client.remove_strategy(strategies[-1][0])

    assert response == {"status": "ok"}
    assert adapters.binance_market_websocket.subscriptions == set()


async def test_bot_http_client_get_account(http_client):
    account = await http_client.get_account()

    assert account == [
        {"symbol": "BTC", "quantity": Decimal("1.0"), "usdt": Decimal("19208.740000000")},
        {"symbol": "ETH", "quantity": Decimal("3.5"), "usdt": Decimal("5706.610000000")},
        {"symbol": "BNB", "quantity": Decimal("10.0"), "usdt": Decimal("2802.000000000")},
        {"symbol": "LTC", "quantity": Decimal("2.0"), "usdt": Decimal("114.840000000")},
        {"symbol": "USDT", "quantity": Decimal("100"), "usdt": Decimal("100")},
        {"symbol": "AMP", "quantity": Decimal("2000.0"), "usdt": Decimal("11.52524400000000000")},
    ]


async def test_bot_http_client_get_pairs(http_client):
    pairs = await http_client.get_pairs()

    assert len(pairs) == 74
