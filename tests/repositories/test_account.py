from binance_analyst.objects import Coin, CoinAmount
from binance_analyst.repositories import get_repositories


def test_account_repository_load(monkeypatch):
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

    account = get_repositories().account.load()

    assert len(account.coins) == 4
    assert account.coins == {
        "BTC": CoinAmount(coin=Coin("BTC"), amount=1),
        "LTC": CoinAmount(coin=Coin("LTC"), amount=2),
        "ETH": CoinAmount(coin=Coin("ETH"), amount=3.5),
        "BNB": CoinAmount(coin=Coin("BNB"), amount=10),
    }
