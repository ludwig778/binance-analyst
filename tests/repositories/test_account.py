from binance_analyst.objects import Coin, CoinAmount


def test_account_repository_load(monkeypatch, repositories):
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_account_info",
        lambda _: {
            "balances": [
                {"asset": "BTC", "free": "1.00000000", "locked": "0.00000000"},
                {"asset": "LTC", "free": "2.00000000", "locked": "0.00000000"},
                {"asset": "ETH", "free": "3.50000000", "locked": "0.00000000"},
                {"asset": "BNB", "free": "10.00000000", "locked": "0.00000000"},
                {"asset": "DOGE", "free": "0.00000000", "locked": "0.00000000"},
            ]
        },
    )

    account = repositories.account.load()

    assert len(account.coins) == 4
    assert account.coins == {
        "BTC": CoinAmount(coin=Coin(name="BTC"), amount=1),
        "LTC": CoinAmount(coin=Coin(name="LTC"), amount=2),
        "ETH": CoinAmount(coin=Coin(name="ETH"), amount=3.5),
        "BNB": CoinAmount(coin=Coin(name="BNB"), amount=10),
    }
