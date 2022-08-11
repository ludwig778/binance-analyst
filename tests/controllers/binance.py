from pytest import raises

from analyst.crypto.exceptions import InvalidPairCoins
from analyst.crypto.models import CoinAmount
from tests.controllers.mocks import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


def test_account_load(adapters, controllers, monkeypatch):
    mock_account_info(adapters, monkeypatch)

    account = controllers.binance.load_account()

    assert len(account) == 4
    assert account == {
        "BTC": CoinAmount(coin="BTC", amount=1),
        "LTC": CoinAmount(coin="LTC", amount=2),
        "ETH": CoinAmount(coin="ETH", amount=3.5),
        "BNB": CoinAmount(coin="BNB", amount=10),
    }


def test_exchange_data_load(adapters, controllers, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = controllers.binance.load_exchange_data()

    assert len(pairs) == 73


def test_pair_repository_filter(adapters, binance_controller, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = binance_controller.load_exchange_data()

    assert (
        len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH", "BNB", "USDT", "BUSD"]))
        == 73
    )
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH"])) == 36
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC"])) == 20
    assert len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "ETH"], exclusive=True)) == 1
    assert (
        len(binance_controller.filter_pairs(pairs, coin_strs=["BTC", "FAKECOIN"], exclusive=True)) == 0
    )


def test_convert_coin(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert binance_controller.convert_coin(CoinAmount(coin="BTC", amount=1), "USDT") == CoinAmount(
        coin="USDT", amount=23954.37
    )

    assert binance_controller.convert_coin(CoinAmount(coin="USDT", amount=1000), "BTC") == CoinAmount(
        coin="BTC", amount=0.04174347466004114
    )

    with raises(InvalidPairCoins):
        binance_controller.convert_coin(CoinAmount(coin="LINT", amount=100), "THETA")


def test_get_transitional_coins(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert binance_controller.get_transitional_coins("BTC", "LINK") == set(["USDT", "BNB", "ETH"])
    assert binance_controller.get_transitional_coins("BNB", "ETH") == set(
        [
            "BTC",
            "USDT",
            "ADA",
            "AVAX",
            "BAT",
            "BUSD",
            "DAI",
            "DOT",
            "LINK",
            "LTC",
            "LUNA",
            "SOL",
            "THETA",
            "UNI",
            "XRP",
            "XTZ",
        ]
    )
    assert binance_controller.get_transitional_coins("ETH", "THETA") == set(["BNB", "USDT", "BTC"])


def test_convert_account_coins(adapters, binance_controller, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    account = {
        "USDT": CoinAmount(coin="USDT", amount=5000),
        "BTC": CoinAmount(coin="BTC", amount=1),
        "ETH": CoinAmount(coin="ETH", amount=2),
        "DOGE": CoinAmount(coin="DOGE", amount=4),
    }

    assert binance_controller.convert_account_coins_to(account=account, to="USDT") == CoinAmount(
        coin="USDT", amount=32640.094559999998
    )

    assert binance_controller.convert_account_coins_to(account=account, to="BTC") == CoinAmount(
        coin="BTC", amount=1.3625612533002056
    )

    assert binance_controller.convert_account_coins_to(account=account, to="LINK") == CoinAmount(
        coin="LINK", amount=3534.3661833159968
    )

    assert binance_controller.convert_account_coins_to(account=account, to="BNB") == CoinAmount(
        coin="BNB", amount=97.5736173869401
    )
