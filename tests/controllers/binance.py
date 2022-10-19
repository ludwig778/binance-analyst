from decimal import Decimal

from pytest import raises

from analyst.crypto.exceptions import InvalidPairCoins
from analyst.crypto.models import CoinAmount
from tests.mocks.common import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


async def test_account_load(adapters, binance_controller, monkeypatch):
    mock_account_info(adapters, monkeypatch)

    account = await binance_controller.load_account()

    assert len(account) == 6
    assert account == {
        "USDT": CoinAmount(coin="USDT", quantity=100),
        "BTC": CoinAmount(coin="BTC", quantity=1),
        "LTC": CoinAmount(coin="LTC", quantity=2),
        "ETH": CoinAmount(coin="ETH", quantity=3.5),
        "BNB": CoinAmount(coin="BNB", quantity=10),
        "AMP": CoinAmount(coin="AMP", quantity=2000),
    }


async def test_load_pairs(adapters, binance_controller, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = await binance_controller.load_pairs()

    assert len(pairs) == 74


async def test_filter_pairs(adapters, binance_controller, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = await binance_controller.load_pairs()

    assert (
        len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH", "BNB", "USDT", "BUSD"])) == 74
    )
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH"])) == 37
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC"])) == 21
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH"], exclusive=True)) == 1
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "FAKECOIN"], exclusive=True)) == 0


async def test_convert_coin(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert await binance_controller.convert_coin(
        CoinAmount(coin="BTC", quantity=1), "USDT"
    ) == CoinAmount(coin="USDT", quantity=19208.74)

    assert await binance_controller.convert_coin(
        CoinAmount(coin="USDT", quantity=1000), "BTC"
    ) == CoinAmount(coin="BTC", quantity=Decimal("0.05206131573522031307592830532"))

    with raises(InvalidPairCoins):
        await binance_controller.convert_coin(CoinAmount(coin="LINT", quantity=100), "THETA")


async def test_get_transitional_coins(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert await binance_controller.get_transitional_coins("BTC", "LINK") == set(["USDT", "BNB", "ETH"])
    assert await binance_controller.get_transitional_coins("BNB", "ETH") == set(
        [
            "BTC",
            "USDT",
            "ADA",
            "AVAX",
            "BUSD",
            "DOT",
            "LINK",
            "LTC",
            "SOL",
            "THETA",
            "UNI",
            "XRP",
            "XTZ",
        ]
    )
    assert await binance_controller.get_transitional_coins("ETH", "THETA") == set(["BNB", "USDT", "BTC"])


async def test_convert_account_coins_to(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    account = {
        "USDT": CoinAmount(coin="USDT", quantity=5000),
        "BTC": CoinAmount(coin="BTC", quantity=1),
        "ETH": CoinAmount(coin="ETH", quantity=2),
        "DOGE": CoinAmount(coin="DOGE", quantity=4),
    }
    pairs = await binance_controller.load_pairs()

    assert await binance_controller.convert_account_coins_to(account=account, to="USDT") == {
        "BTC": Decimal("19208.74000000"),
        "DOGE": Decimal("0.24124000"),
        "ETH": Decimal("3260.92000000"),
        "USDT": Decimal("5000"),
    }

    assert await binance_controller.convert_account_coins_to(account=account, to="BTC") == {
        "BTC": Decimal("1"),
        "DOGE": Decimal("0.00001256"),
        "ETH": Decimal("0.16975000"),
        "USDT": Decimal("0.2603065786761015653796415266"),
    }

    assert await binance_controller.convert_account_coins_to(account=account, to="LINK", pairs=pairs) == {
        "BTC": Decimal("2600.780234070221066319895969"),
        "DOGE": Decimal("0.03266579973992197659297789337"),
        "ETH": Decimal("441.6961130742049469964664311"),
        "USDT": Decimal("676.9564040075819117248849174"),
    }

    assert await binance_controller.convert_account_coins_to(account=account, to="BNB", pairs=pairs) == {
        "BTC": Decimal("68.55889208830385300973536268"),
        "DOGE": Decimal("0.0008612638343448768297036772581"),
        "ETH": Decimal("11.64144353899883585564610012"),
        "USDT": Decimal("17.85076758300606926097822206"),
    }
