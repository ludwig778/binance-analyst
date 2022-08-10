from pytest import raises

from analyst.controllers.binance import (
    convert_account_coins_to,
    convert_coin,
    filter_pairs,
    get_transitional_coins,
    load_account,
    load_exchange_data,
)
from analyst.crypto.exceptions import InvalidPairCoins
from analyst.crypto.models import CoinAmount
from tests.controllers.mocks import mock_account_info, mock_exchange_data_info, mock_pair_prices_info


def test_account_load(adapters, monkeypatch):
    mock_account_info(adapters, monkeypatch)

    account = load_account(adapters)

    assert len(account) == 4
    assert account == {
        "BTC": CoinAmount(coin="BTC", amount=1),
        "LTC": CoinAmount(coin="LTC", amount=2),
        "ETH": CoinAmount(coin="ETH", amount=3.5),
        "BNB": CoinAmount(coin="BNB", amount=10),
    }


def test_exchange_data_load(adapters, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = load_exchange_data(adapters)

    assert len(pairs) == 73


def test_pair_repository_filter(adapters, monkeypatch):
    mock_exchange_data_info(adapters, monkeypatch)

    pairs = load_exchange_data(adapters)

    assert len(filter_pairs(pairs, coin_strs=["BTC", "ETH", "BNB", "USDT", "BUSD"])) == 73
    assert len(filter_pairs(pairs, coin_strs=["BTC", "ETH"])) == 36
    assert len(filter_pairs(pairs, coin_strs=["BTC"])) == 20
    assert len(filter_pairs(pairs, coin_strs=["BTC", "ETH"], exclusive=True)) == 1
    assert len(filter_pairs(pairs, coin_strs=["BTC", "FAKECOIN"], exclusive=True)) == 0


def test_convert_coin(adapters, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert convert_coin(adapters, CoinAmount(coin="BTC", amount=1), "USDT") == CoinAmount(
        coin="USDT", amount=23954.37
    )

    assert convert_coin(adapters, CoinAmount(coin="USDT", amount=1000), "BTC") == CoinAmount(
        coin="BTC", amount=0.04174347466004114
    )

    with raises(InvalidPairCoins):
        convert_coin(adapters, CoinAmount(coin="LINT", amount=100), "THETA")


def test_get_transitional_coins(adapters, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    assert get_transitional_coins(adapters, "BTC", "LINK") == set(["USDT", "BNB", "ETH"])
    assert get_transitional_coins(adapters, "BNB", "ETH") == set(
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
    assert get_transitional_coins(adapters, "ETH", "THETA") == set(["BNB", "USDT", "BTC"])


def test_convert_account_coins(adapters, monkeypatch):
    mock_pair_prices_info(adapters, monkeypatch)

    account = {
        "USDT": CoinAmount(coin="USDT", amount=5000),
        "BTC": CoinAmount(coin="BTC", amount=1),
        "ETH": CoinAmount(coin="ETH", amount=2),
        "DOGE": CoinAmount(coin="DOGE", amount=4),
    }

    assert convert_account_coins_to(adapters=adapters, account=account, to="USDT") == CoinAmount(
        coin="USDT", amount=32640.094559999998
    )

    assert convert_account_coins_to(adapters=adapters, account=account, to="BTC") == CoinAmount(
        coin="BTC", amount=1.3625612533002056
    )

    assert convert_account_coins_to(adapters=adapters, account=account, to="LINK") == CoinAmount(
        coin="LINK", amount=3534.3661833159968
    )

    assert convert_account_coins_to(adapters=adapters, account=account, to="BNB") == CoinAmount(
        coin="BNB", amount=97.5736173869401
    )
