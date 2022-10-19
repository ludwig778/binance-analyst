import asyncio

from pytest import fixture
from tabulate import tabulate

from analyst.bot.order_manager import OrderManager
from analyst.controllers.factory import Controllers


@fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@fixture(scope="session")
async def controllers(functionnal_controllers):
    return functionnal_controllers


async def test_order_manager(controllers: Controllers):
    pairs = await controllers.binance.load_pairs()

    print("\n")
    print("Pair numbers: ", len(pairs))

    btcusdt = pairs["BTCUSDT"]

    symbols = [
        "BTSBTC",
        "GTOBTC",
        "IOSTBTC",
        "QKCBTC",
        "DOCKBTC",
        "CELRBTC",
        "COSBTC",
        "PERLBTC",
        "TCTBTC",
        "STMXBTC",
        "DGBBTC",
        "IRISBTC",
        "FORBTC",
        "PONDBTC",
        "LINABTC",
        "QIBTC",
        "JASMYBTC",
        "AMPBTC",
        "ACHBTC",
    ]

    ampbtc = pairs["AMPBTC"]
    print()

    def show(obj):
        print(tabulate(obj.dict().items(), tablefmt="simple"))

    show(ampbtc)

    man = OrderManager(controllers)
    await man.load_account()

    order = await man.buy(ampbtc, 0.00405)

    show(order)

    print(btcusdt.bid_price)
    btc_amount = 100 / btcusdt.bid_price
    print(f"{btc_amount=}")

    print(btc_amount / ampbtc.bid_price)
    print(btc_amount / ampbtc.bid_price)

    for symbol in symbols:
        pair = pairs[symbol]
        print(
            f"{symbol:8s}, "
            f"{pair.max_quantity:10.1f}, "
            f"{pair.min_quantity:4.1f}, "
            f"{pair.step_size}, "
            f"{0.004 / pair.bid_price:10.1f}, ",
            man._get_min_buy_value(pair, 0.004),
        )

    from pprint import pprint

    pprint(man._account)
    await man._get_max_account_pair_value(pairs["PERLBTC"])
