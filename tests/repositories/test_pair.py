from datetime import datetime

from pandas import DataFrame, DatetimeIndex

from binance_analyst.objects import Coin, Pair
from binance_analyst.repositories import get_repositories


def test_pair_repository_load(monkeypatch):
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_historical_klines",
        lambda *_: [
            [
                1644451200000,  # Open time
                "0.07309600",  # Open
                "0.07340600",  # High
                "0.07015900",  # Low
                "0.07064200",  # Close
                "73001.58190000",  # Volume
                1644537599999,  # Close time
                "5227.37648417",  # Quote asset volume
                179510,  # Trades
                "36718.53130000",  # Taker buy base asset volume
                "2627.81608618",  # Taker buy base asset volume
                "0",  # Ignore
            ],
            [
                1644537600000,
                "0.07063800",
                "0.07165700",
                "0.06873300",
                "0.06887200",
                "47333.19550000",
                1644623999999,
                "3344.60108893",
                132050,
                "23683.64340000",
                "1674.16354128",
                "0",
            ],
        ],
    )

    pair = Pair(Coin("ETH"), Coin("BTC"))

    klines = get_repositories().pair.get_klines(pair)

    forged = DataFrame(
        [
            {
                "timestamp": datetime(2022, 2, 11),
                "open": 0.073096,
                "high": 0.073406,
                "low": 0.070159,
                "close": 0.070642,
                "volumes": 73001.5819,
                "trades": 179510.0,
            },
            {
                "timestamp": datetime(2022, 2, 12),
                "open": 0.070638,
                "high": 0.071657,
                "low": 0.068733,
                "close": 0.068872,
                "volumes": 47333.1955,
                "trades": 132050.0,
            },
        ],
    )
    forged["timestamp"] = DatetimeIndex(forged["timestamp"])
    forged.set_index("timestamp", inplace=True)

    assert klines.equals(forged)
