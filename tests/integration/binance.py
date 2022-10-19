import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pprint import pprint

from pytest import fixture, raises
from tabulate import tabulate

from analyst.crypto.models import CoinAmount


@fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@fixture(scope="session")
async def controllers(functionnal_controllers):
    return functionnal_controllers


async def test_load_account(controllers):
    account = await controllers.binance.load_account()

    print()
    print("Account :")
    print(
        tabulate(
            [
                {"coin": asset.coin, "quantity": asset.quantity}
                for asset in sorted(account.values(), key=lambda x: x.quantity, reverse=True)
            ],
            headers="keys",
        )
    )


async def test_load_pairs(controllers):
    pairs = await controllers.binance.load_pairs()

    print()
    print("Exchange data :")
    print("BTCUSDT :")
    print(tabulate(pairs["BTCUSDT"].dict().items(), tablefmt="simple"))


async def test_get_order_book(controllers):
    order_book = await controllers.binance.get_order_book("AMPBTC")

    print()
    print("Order Book :")
    print(order_book)


async def test_get_klines(controllers):
    start_datetime = datetime.now() - timedelta(hours=4)
    end_datetime = datetime.now()

    df = await controllers.binance.get_klines(
        symbol="BTCUSDT", interval="1h", start_datetime=start_datetime, end_datetime=end_datetime
    )

    print()
    print(f"Get Klines : start={df.iloc[-1].name} end={df.iloc[0].name} len={len(df.close)}")
    print(df)


async def test_load_dataframes(controllers):
    start_datetime = datetime.now() - timedelta(hours=4)
    end_datetime = datetime.now()

    pairs = await controllers.binance.load_pairs()
    pairs = {symbol: pair for symbol, pair in pairs.items() if symbol in ["BTCUSDT", "ETHBTC"]}

    df = await controllers.binance.load_dataframes(
        pairs=pairs, interval="1h", start_datetime=start_datetime, end_datetime=end_datetime
    )

    print()
    print(
        f"Load DataFrame : start={df.iloc[-1].name} end={df.iloc[0].name} "
        f"symbols={', '.join(df.columns.get_level_values(0).unique())}"
    )


async def test_convert_coin(controllers):
    btc = CoinAmount(coin="BTC", quantity=1)

    usdt = await controllers.binance.convert_coin(asset=btc, to="USDT")

    print()
    print(f"Convert coin : {btc.quantity} BTC => {usdt.quantity} USDT")


async def test_get_transitional_coins(controllers):
    transitional_coins = await controllers.binance.get_transitional_coins(origin="DOGE", dest="LINK")

    print()
    print(f"Transitional coins (DOGE => LINK): {', '.join(transitional_coins)}")


async def test_convert_transitional_coins(controllers):
    pairs = await controllers.binance.load_pairs()

    origin = "DOGE"
    dest = "ETH"

    transitional_coins_conversions = await controllers.binance.convert_transitional_coins(
        asset=CoinAmount(coin=origin, quantity=1), dest=dest, pairs=pairs
    )

    print()
    print(f"Transitional coins ({origin} => {dest}):")
    for symbol, quantity in sorted(
        transitional_coins_conversions.items(), key=lambda x: x[1], reverse=True
    ):
        print(f" {symbol:5s} = {quantity:10.10f}")


async def test_convert_account_coins_to(controllers):
    account = await controllers.binance.load_account()

    dest = "USDT"

    converted_account = await controllers.binance.convert_account_coins_to(account=account, to=dest)

    print()
    print(f"Convert Account to {dest}:")
    for symbol, quantity in sorted(converted_account.items(), key=lambda x: x[1], reverse=True):
        print(f"{account[symbol].quantity:14f} {symbol:5s} = {quantity:7f} {dest}")

    print(f"Total: {sum(converted_account.values()):7f} {dest}")


async def test_listen_market_streams(controllers):
    async def run_loop():
        async for stream_name, ticker_data in controllers.binance.listen_market_streams(
            ["ampbtc@ticker"]
        ):
            print(stream_name)
            pprint(ticker_data.dict())

    try:
        print()
        print("Starting Market Stream WebSocket:")

        await asyncio.wait_for(run_loop(), timeout=15)
    except asyncio.TimeoutError:
        print("Closing WebSocket...")
        await controllers.binance.adapters.binance_market_websocket.close()


async def test_get_metadata(controllers):
    adapters = controllers.binance.adapters
    metadata = await adapters.binance.get_metadata()

    print()
    print("Current Weight:")
    pprint(f"  {adapters.binance.weights}")
    print("Fetched Metadata:")
    pprint(metadata.dict())


async def test_create_order(controllers):
    pairs = await controllers.binance.load_pairs()

    btcusdt = pairs["BTCUSDT"]

    await controllers.binance.create_test_order(
        symbol="BTCUSDT", side="BUY", type="MARKET", quote_quantity=float(btcusdt.quote_min_amount)
    )

    await controllers.binance.create_test_order(
        symbol="BTCUSDT",
        side="BUY",
        type="LIMIT",
        time_in_force="GTC",
        price=40000,
        quantity=float(btcusdt.base_min_quantity),
    )

    await controllers.binance.create_test_order(
        symbol="BTCUSDT", side="BUY", type="MARKET", quote_quantity=float(btcusdt.quote_min_amount)
    )

    await controllers.binance.create_test_order(
        symbol="BTCUSDT",
        side="BUY",
        type="LIMIT_MAKER",
        price=50000,
        quantity=float(btcusdt.max_quantity),
    )

    with raises(Exception, match="Filter failure: MIN_NOTIONAL"):
        await controllers.binance.create_test_order(
            symbol="BTCUSDT",
            side="BUY",
            type="MARKET",
            quote_quantity=float(btcusdt.base_min_quantity - Decimal("0.0001")),
        )

    with raises(Exception, match="Illegal characters found in parameter 'quantity';"):
        await controllers.binance.create_test_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT_MAKER", price=50000, quantity=0.00001
        )

    with raises(Exception, match="Parameter 'price' sent when not required."):
        await controllers.binance.create_test_order(
            symbol="BTCUSDT", side="BUY", type="MARKET", price=50000, quantity=0.1
        )

    with raises(
        Exception, match="Mandatory parameter 'price' was not sent, was empty/null, or malformed."
    ):
        await controllers.binance.create_test_order(
            symbol="BTCUSDT", side="BUY", type="LIMIT_MAKER", quantity=0.1
        )


async def test_get_order(controllers):
    last_order_id = (await controllers.binance.list_orders("BTCUSDT"))[-1].id

    order = await controllers.binance.get_order("BTCUSDT", last_order_id)

    print()
    print("Last Order: (BTCUSDT)")
    print(tabulate(order.dict().items(), tablefmt="simple"))


async def test_list_orders(controllers):
    orders = await controllers.binance.list_orders("BTCUSDT")

    print()
    print("Orders: (BTCUSDT)")
    print(tabulate([order.dict() for order in orders], headers="keys"))
