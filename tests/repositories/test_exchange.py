from binance_analyst.adapters.binance import TickerPrices
from binance_analyst.objects import Coin, CoinAmount


def test_exchange_repository_load(monkeypatch, repositories):
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_prices",
        lambda *_: TickerPrices(
            prices={
                ticker_data.get("symbol"): ticker_data
                for ticker_data in [
                    {"askPrice": 0.7679, "bidPrice": 0.7676, "symbol": "BATUSDT"},
                    {"askPrice": 0.009949, "bidPrice": 0.009948, "symbol": "BNBBTC"},
                    {"askPrice": 404.5, "bidPrice": 404.4, "symbol": "BNBUSDT"},
                    {"askPrice": 40660.31, "bidPrice": 40660.3, "symbol": "BTCUSDT"},
                    {"askPrice": 0.1397, "bidPrice": 0.1396, "symbol": "DOGEUSDT"},
                    {"askPrice": 0.071171, "bidPrice": 0.071168, "symbol": "ETHBTC"},
                    {"askPrice": 15.66, "bidPrice": 15.65, "symbol": "LINKUSDT"},
                    {"askPrice": 116.8, "bidPrice": 116.7, "symbol": "LTCUSDT"},
                    {"askPrice": 93.9, "bidPrice": 93.89, "symbol": "SOLUSDT"},
                    {"askPrice": 0.7749, "bidPrice": 0.7748, "symbol": "XRPUSDT"},
                ]
            }
        ),
    )

    exchange_data = repositories.exchange.load()

    assert len(exchange_data.prices) == 10

    assert exchange_data.prices["BTCUSDT"].ask == 40660.31
    assert exchange_data.prices["BTCUSDT"].bid == 40660.3


def test_exchange_repository_convert(monkeypatch, repositories):
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_prices",
        lambda *_: TickerPrices(
            prices={
                "BTCUSDT": {"askPrice": 40660.31, "bidPrice": 40660.3},
            }
        ),
    )

    asset = CoinAmount(coin=Coin(name="USDT"), amount=10000)
    converted = repositories.exchange.convert(asset, Coin(name="BTC"))

    assert converted.amount == 0.24594008260143616

    asset = CoinAmount(coin=Coin(name="BTC"), amount=1)
    converted = repositories.exchange.convert(asset, Coin(name="USDT"))

    assert converted.amount == 40660.3


def test_exchange_repository_convert_with_given_prices(repositories):
    exchange_data = TickerPrices(prices={"BTCUSDT": {"askPrice": 40660.31, "bidPrice": 40660.3}})

    asset = CoinAmount(coin=Coin(name="USDT"), amount=10000)
    converted = repositories.exchange.convert(asset, Coin(name="BTC"), exchange_prices=exchange_data)

    assert converted.amount == 0.24594008260143616

    asset = CoinAmount(coin=Coin(name="BTC"), amount=1)
    converted = repositories.exchange.convert(asset, Coin(name="USDT"), exchange_prices=exchange_data)

    assert converted.amount == 40660.3
