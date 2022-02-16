from __future__ import annotations

import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict

from pandas import DataFrame, DatetimeIndex, concat

from binance_analyst.exceptions import InvalidInterval, WrongDatetimeRange
from binance_analyst.objects import Coin, Pair
from binance_analyst.repositories.base import AdaptersAwareRepository

Pairs = Dict[str, Pair]
PairsDataframes = Dict[str, DataFrame]

datetime_format = "%Y-%m-%d_%H:%M:%S"


class PairRepository(AdaptersAwareRepository):
    possible_intervals = [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    ]

    def load(self) -> Pairs:
        filename = "symbols.json"

        data = None
        if self.adapters.metadata.exists(filename):
            data = self.adapters.metadata.load(filename)

        if not data:
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

    def _get_klines(
        self,
        pair: Pair,
        interval: str = "1d",
        start_datetime: datetime = datetime(2000, 1, 1),
        end_datetime: datetime = datetime.now(),
    ) -> DataFrame:
        if start_datetime < datetime(2000, 1, 1):
            raise WrongDatetimeRange(start_datetime)
        elif start_datetime < datetime(2000, 1, 1):
            raise WrongDatetimeRange(end_datetime)
        elif interval not in self.possible_intervals:
            raise InvalidInterval(interval)

        unit_value, interval_unit = interval[:-1], interval[-1]

        if interval == "1M":
            shift_delta = timedelta(days=30)
        elif interval == "1w":
            shift_delta = timedelta(weeks=1)
        elif interval_unit == "d":
            shift_delta = timedelta(days=int(unit_value))
        elif interval_unit == "h":
            shift_delta = timedelta(hours=int(unit_value))
        elif interval_unit == "m":
            shift_delta = timedelta(minutes=int(unit_value))

        start_datetime -= shift_delta
        end_datetime -= shift_delta

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
            for kline_data in self.adapters.binance.get_historical_klines(
                symbol=pair.symbol,
                interval=interval,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
            )
        ]

        df = DataFrame(klines)

        if not df.empty:
            df["timestamp"] = DatetimeIndex(df["timestamp"])
            df.set_index("timestamp", inplace=True)

            if interval == "1d":
                df = df.resample("D").mean()

        return df

    def get_klines(
        self,
        pair: Pair,
        interval: str = "1d",
        start_datetime: datetime = datetime(1970, 1, 1),
        end_datetime: datetime = datetime.now(),
        no_cache: bool = False,
        saving: bool = False,
        full: bool = False,
    ) -> DataFrame:
        if full:
            filename = "{}_{}_full.json".format(
                pair.symbol,
                interval,
            )
        else:
            filename = "{}_{}_{}_{}.json".format(
                pair.symbol,
                interval,
                start_datetime.strftime(datetime_format),
                end_datetime.strftime(datetime_format),
            )

        df = DataFrame()
        if self.adapters.dataframe.exists(filename) and not no_cache:
            df = self.adapters.dataframe.load(filename)

            if not full:
                return df

            if df.empty:
                df = self.get_klines(pair, interval, start_datetime, end_datetime)
            else:
                first_datetime = df.index[0].to_pydatetime()
                last_datetime = df.index[-1].to_pydatetime()

                if (
                    start_datetime < first_datetime
                    and not (
                        pre_df := self.get_klines(pair, interval, start_datetime, first_datetime)
                    ).empty
                ):
                    df = concat([pre_df, df])
                    df = df[~df.index.duplicated()]

                if (
                    last_datetime < end_datetime
                    and not (
                        post_df := self.get_klines(pair, interval, last_datetime, end_datetime)
                    ).empty
                ):
                    df = concat([post_df, df])
                    df = df[~df.index.duplicated()]

        else:
            df = self._get_klines(
                pair=pair,
                interval=interval,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
            )

        if saving:
            self.adapters.dataframe.save(filename, df)

        return df

    def load_dataframes(self, pairs: Pairs, workers=5, **kwargs) -> PairsDataframes:
        dataframes = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.get_klines, pair, **kwargs): symbol
                for symbol, pair in pairs.items()
            }
            for future in as_completed(futures):
                symbol = futures[future]
                dataframes[symbol] = future.result()

        return dataframes
