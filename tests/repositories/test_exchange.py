from pytest import raises

from binance_analyst.adapters.binance import TickerPrices
from binance_analyst.exceptions import InvalidPairCoins
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
                    {"askPrice": 2771.34, "bidPrice": 2771.33, "symbol": "ETHUSDT"},
                    {"askPrice": 15.66, "bidPrice": 15.65, "symbol": "LINKUSDT"},
                    {"askPrice": 116.8, "bidPrice": 116.7, "symbol": "LTCUSDT"},
                    {"askPrice": 93.9, "bidPrice": 93.89, "symbol": "SOLUSDT"},
                    {"askPrice": 0.7749, "bidPrice": 0.7748, "symbol": "XRPUSDT"},
                ]
            }
        ),
    )

    exchange_data = repositories.exchange.load()

    assert len(exchange_data.prices) == 11

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


def test_exchange_repository_convert_raise_symbol_not_found(repositories):
    with raises(InvalidPairCoins, match="USDT-BTC"):
        repositories.exchange.convert(
            CoinAmount(coin=Coin(name="USDT"), amount=10000),
            Coin(name="BTC"),
            exchange_prices=TickerPrices(prices={}),
        )


def test_exchange_repository_get_transitional_coins(monkeypatch, repositories):
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

    assert repositories.exchange.get_transitional_coins(
        Coin(name="BTC"), Coin(name="LINK"), exchange_prices=exchange_data
    ) == set([Coin("USDT")])

    assert repositories.exchange.get_transitional_coins(Coin(name="BNB"), Coin(name="ETH")) == set(
        [Coin(name="BTC"), Coin(name="USDT")]
    )

    assert repositories.exchange.get_transitional_coins(Coin(name="ETH"), Coin(name="THETA")) == set()
