from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from pytest import fixture, mark

from analyst.adapters.binance import BinanceWebSocketAdapter
from analyst.bot.bot import Runner
from analyst.bot.strategies.market_maker import MarketMakerV1
from analyst.controllers.binance import BinanceController
from analyst.crypto.models import MarketStreamTicker
from tests.mocks.common import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


@fixture(scope="function", autouse=True)
async def clean_repositories(repositories):
    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()

    yield

    await repositories.strategies.delete_all()
    await repositories.orders.delete_all()


@fixture(scope="function", autouse=True)
async def setup_websocket_server(monkeypatch):
    async def mocked_send(*args, **kwargs):
        pass

    monkeypatch.setattr(BinanceWebSocketAdapter, "send", mocked_send)


@fixture(scope="function", autouse=True)
async def setup_mocks(adapters, monkeypatch, order_manager):
    mock_account_info(adapters, monkeypatch)
    mock_exchange_data_info(adapters, monkeypatch)
    mock_pair_prices_info(adapters, monkeypatch)

    async def mock_get_updated_order(order):
        return deepcopy(order)

    monkeypatch.setattr(order_manager.controllers.binance, "get_updated_order", mock_get_updated_order)

    await order_manager.setup()


@fixture(scope="function")
def runner(controllers, order_manager):
    return Runner(
        controllers=controllers,
        order_manager=order_manager,
    )


async def test_bot_runner_setup(runner, order_manager, controllers):
    strategy = MarketMakerV1.create(
        symbol="AMPBTC",
        quote_quantity=Decimal("0.004"),
    )

    await strategy.setup(order_manager)
    await controllers.mongo.store_strategy(strategy)

    await runner.setup()

    assert strategy.id in runner.strategies
    assert set(strategy.get_stream_names()) == set(runner.strategies_by_streams.keys())


async def test_bot_runner_add_strategy(runner, controllers):
    added, exception_str = await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "AMPBTC", "quote_quantity": "0.004"}
    )

    assert added
    assert not exception_str

    strategies = await controllers.mongo.get_running_strategies()

    assert len(strategies) == 1
    assert strategies[0].id in runner.strategies


async def test_bot_runner_add_strategy_wrong_symbol_exception(runner, controllers):
    added, exception_str = await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "FAKEBTC", "quote_quantity": "0.004"}
    )
    assert not added
    assert "Pair FAKEBTC does not exist strategy_id=" in exception_str

    strategies = await controllers.mongo.get_running_strategies()

    assert len(strategies) == 0


async def test_bot_runner_add_strategy_insufficient_amount_exception(runner, controllers):
    added, exception_str = await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "AMPBTC", "quote_quantity": "1.5"}
    )
    assert not added
    assert "Insufficient funds strategy_id=" in exception_str

    strategies = await controllers.mongo.get_running_strategies()

    assert len(strategies) == 0


async def test_bot_runner_add_strategy_missing_symbol_exception(runner, controllers):
    added, exception_str = await runner.add_strategy(
        name="market_maker", version="v1", args={"quote_quantity": "0.004"}
    )

    assert not added
    assert exception_str == "__init__() missing 1 required positional argument: 'symbol'"


async def test_bot_runner_stop_strategy(runner, controllers):
    await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "AMPBTC", "quote_quantity": "0.004"}
    )

    strategies = await controllers.mongo.get_running_strategies()

    assert len(strategies) == 1

    stopped, exception_str = await runner.stop_strategy(strategies[0].id)

    assert stopped
    assert exception_str == ""

    stopped, exception_str = await runner.stop_strategy(strategies[0].id)

    assert stopped
    assert exception_str == "Nothing to do, state is stopping"

    assert strategies[0].id in runner.strategies


async def test_bot_runner_stop_strategy_not_found_exception(runner):
    stopped, exception_str = await runner.stop_strategy(uuid4())

    assert not stopped
    assert exception_str == "Could not find strategy"


async def test_bot_runner_remove_strategy(runner, controllers):
    await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "AMPBTC", "quote_quantity": "0.004"}
    )

    strategies = await controllers.mongo.get_running_strategies()

    assert len(strategies) == 1

    removed, exception_str = await runner.remove_strategy(strategies[0].id)

    assert strategies[0].id not in runner.strategies

    assert removed
    assert exception_str == ""

    removed, exception_str = await runner.remove_strategy(strategies[0].id)

    assert not removed
    assert exception_str == "Could not find strategy"


@mark.skip
async def test_bot_runner_test(runner, controllers, order_manager, monkeypatch):
    class OutOfMock(Exception):
        pass

    def mocked_send(runner: Runner):
        async def mocked(*args, **kwargs):
            strategy = list(runner.strategies.values())[0]

            balanced_quantity_ticker = MarketStreamTicker(
                symbol="AMPBTC",
                last_price=Decimal("0.00000028"),
                ask_price=Decimal("0.00000029"),
                ask_quantity=Decimal("1_000_000"),
                bid_price=Decimal("0.00000028"),
                bid_quantity=Decimal("1_000_000"),
                trades=500,
            )
            low_bid_quantity_ticker = MarketStreamTicker(
                symbol="AMPBTC",
                last_price=Decimal("0.00000028"),
                ask_price=Decimal("0.00000029"),
                ask_quantity=Decimal("1_000_000"),
                bid_price=Decimal("0.00000028"),
                bid_quantity=Decimal("50_000"),
                trades=500,
            )

            yield "ampbtc@ticker", balanced_quantity_ticker

            order = runner.order_manager.get_order(strategy.internal_order_id)
            order.executed_quantity = order.requested_quantity / 3

            filled_buy = await runner.order_manager.update_order(order)

            await strategy.process_order(filled_buy, runner.order_manager)

            yield "ampbtc@ticker", low_bid_quantity_ticker

            filled_sell = await runner.order_manager.fill_order(
                runner.order_manager.get_order(strategy.internal_order_id)
            )

            await strategy.process_order(filled_sell, runner.order_manager)

            yield "ampbtc@ticker", low_bid_quantity_ticker

            assert not strategy.internal_order_id

            yield "ampbtc@ticker", balanced_quantity_ticker

            assert strategy.internal_order_id

            raise OutOfMock()

        return mocked

    monkeypatch.setattr(BinanceController, "listen_market_streams", mocked_send(runner))

    await runner.add_strategy(
        name="market_maker", version="v1", args={"symbol": "AMPBTC", "quote_quantity": "0.004"}
    )

    try:
        await runner.run_market_streams()
    except OutOfMock:
        pass
