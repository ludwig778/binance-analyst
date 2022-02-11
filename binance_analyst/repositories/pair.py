from __future__ import annotations

import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict

from pandas import DataFrame, DatetimeIndex

from binance_analyst.objects import Coin, Pair
from binance_analyst.repositories.base import AdaptersAwareRepository

Pairs = Dict[str, Pair]


class PairRepository(AdaptersAwareRepository):
    # @cached(cache=TTLCache(maxsize=1, ttl=600))
    def get_klines(self, pair: Pair, interval="1d", no_cache=False):
        filename = f"{pair.symbol}_{interval}.json"

        df = DataFrame()
        if self.adapters.dataframe.exists(filename):
            df = self.adapters.dataframe.load(filename)

        if df.empty or no_cache:
            klines = [
                {
                    "timestamp": datetime.fromtimestamp((kline_data[6] + 1) / 1000),
                    "open": float(kline_data[1]),
                    "high": float(kline_data[2]),
                    "low": float(kline_data[3]),
                    "close": float(kline_data[4]),
                    "volumes": float(kline_data[5]),
                    "trades": kline_data[8],
                }
                for kline_data in self.adapters.binance.get_historical_klines(pair.symbol, interval)
            ]

            df = DataFrame(klines)
            df["timestamp"] = DatetimeIndex(df["timestamp"])
            df.set_index("timestamp", inplace=True)

            if interval == "1d":
                df = df.resample("D").mean()

            self.adapters.dataframe.save(filename, df)

        return df

    def load(self) -> Pairs:
        filename = "symbols.json"

        if not (data := self.adapters.metadata.load(filename)):
            data = {
                coin_data.get("symbol"): [coin_data.get("baseAsset"), coin_data.get("quoteAsset")]
                for coin_data in self.adapters.binance.get_exchange_info()
            }
            self.adapters.metadata.save(filename, data)

        return {symbol: Pair(*map(Coin, coins)) for symbol, coins in data.items()}

    def filter(self, pairs: Pairs, coin_strs: list[str], exclusive=False) -> Pairs:
        op = operator.__and__ if exclusive else operator.__or__
        return {
            symbol: pair
            for symbol, pair in pairs.items()
            if op(pair.base.name in coin_strs, pair.quote.name in coin_strs)
        }

    def load_dataframes(self, pairs: Pairs, interval="1d", workers=5):
        dataframes = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.get_klines, pair, interval, no_cache=False): pair.symbol
                for symbol, pair in pairs.items()
            }
            for future in as_completed(futures):
                symbol = futures[future]
                dataframes[symbol] = future.result()

        return dataframes
