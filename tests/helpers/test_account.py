from binance_analyst.adapters.binance import TickerPrices
from binance_analyst.helpers.account import convert_account_coins_to
from binance_analyst.models import Account, Coin, CoinAmount


def test_convert_account_coins_to(controllers, monkeypatch):
    exchange_data = TickerPrices(
        prices={
            "BNBBTC": {"askPrice": 0.009949, "bidPrice": 0.009948},
            "BNBUSDT": {"askPrice": 404.5, "bidPrice": 404.4},
            "BTCUSDT": {"askPrice": 40660.31, "bidPrice": 40660.3},
            "DOGEUSDT": {"askPrice": 0.1397, "bidPrice": 0.1396},
            "ETHBTC": {"askPrice": 0.071171, "bidPrice": 0.071168},
            "ETHUSDT": {"askPrice": 2771.34, "bidPrice": 2771.33},
            "LINKUSDT": {"askPrice": 15.66, "bidPrice": 15.65},
        }
    )
    monkeypatch.setattr("binance_analyst.adapters.BinanceAdapter.get_prices", lambda *_: exchange_data)

    account = Account(
        coins={
            "USDT": CoinAmount(coin=Coin(name="USDT"), amount=5000),
            "BTC": CoinAmount(coin=Coin(name="BTC"), amount=1),
            "ETH": CoinAmount(coin=Coin(name="ETH"), amount=2),
            "DOGE": CoinAmount(coin=Coin(name="DOGE"), amount=4),
        }
    )

    assert convert_account_coins_to(
        controllers=controllers, account=account, to=Coin("USDT")
    ) == CoinAmount(coin=Coin(name="USDT"), amount=51203.51840000001)

    assert convert_account_coins_to(
        controllers=controllers, account=account, to=Coin("BTC")
    ) == CoinAmount(coin=Coin(name="BTC"), amount=1.2653197745949305)

    assert convert_account_coins_to(
        controllers=controllers, account=account, to=Coin("LINK")
    ) == CoinAmount(coin=Coin(name="LINK"), amount=3269.7010472541506)

    assert convert_account_coins_to(
        controllers=controllers, account=account, to=Coin("BNB")
    ) == CoinAmount(coin=Coin(name="BNB"), amount=127.18149770792725)
