import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

import matplotlib.pyplot as plt
from pandas import DataFrame

from analyst.controllers.factory import Controllers
from analyst.crypto.models import Pairs


class MarketMakerScreener:
    def __init__(
        self,
        controllers: Controllers,
        pairs: Optional[Pairs] = None,
        df_5m: Optional[DataFrame] = None,
        df_1h: Optional[DataFrame] = None,
    ):
        self.controllers = controllers
        self.pairs = pairs

        self.df_1h = df_5m
        self.df_5m = df_1h

    async def load_pairs(self):
        pairs = await self.controllers.binance.load_pairs()

        self.pairs = self.controllers.binance.filter_pairs(pairs, ["BTC"])

    async def load_1h_dataframe(self):
        self.df_1h = await self.controllers.binance.load_dataframes(
            self.pairs,
            interval="1h",
            start_datetime=datetime.now() - timedelta(days=60),
            end_datetime=datetime.now(),
        )

    async def load_5m_dataframe(self):
        self.df_5m = await self.controllers.binance.load_dataframes(
            self.pairs,
            interval="5m",
            start_datetime=datetime.now() - timedelta(minutes=5 * 990),
            end_datetime=datetime.now(),
        )

    async def load_dataframes(self):
        await asyncio.gather(self.load_5m_dataframe(), self.load_1h_dataframe())

    def format_screen_result(self, screen_result):
        format_style = {
            column_name: style
            for style, column_names in {
                "{:,.0f}": ["1d_vol", "last_1d_vol", "ask_q", "bid_q"],
                "{:.1f}%": ["1d_lvl", "7d_lvl"],
                "{:.1f}": ["b/a", "fill ask", "fill bid"],
                "{:.2f}%": ["diff"],
                "{:.8f}": ["ask", "bid"],
            }.items()
            for column_name in column_names
        }
        return screen_result.style.format(format_style)

    def _get_ask_bid_price_changes(self, df: DataFrame) -> int:
        bounds: List[int] = []
        last = None
        changes = 0

        for value in df.close.values:
            if not bounds:
                bounds = [value, value]

            elif value not in bounds:
                if bounds[0] != bounds[1]:
                    changes += 1

            if bounds and last and value < last:
                bounds = [last, value]
            elif bounds and last and value > last:
                bounds = [value, last]

            last = value

        return changes

    def run(self):
        screen_data = []

        for symbol, pair in self.pairs.items():
            if pair.ask_price == 0 and pair.bid_price == 0:
                continue

            df_2m = self.df_1h[symbol][self.df_1h.iloc[-1].name - timedelta(days=60):]
            df_1m = self.df_1h[symbol][self.df_1h.iloc[-1].name - timedelta(days=30):]
            df_1w = self.df_1h[symbol][self.df_1h.iloc[-1].name - timedelta(days=7):]
            prev_df_1d = self.df_5m[symbol][
                self.df_5m.iloc[-1].name
                - timedelta(days=2):self.df_5m.iloc[-1].name
                - timedelta(days=1)
            ]
            df_1d = self.df_5m[symbol][self.df_5m.iloc[-1].name - timedelta(days=1):]
            df_3h = self.df_5m[symbol][self.df_5m.iloc[-1].name - timedelta(hours=3):]

            susc_perc = ((pair.ask_price - pair.bid_price) / pair.bid_price) * 100

            def get_value(df):
                den = float(round(df.close.max() - df.close.min(), 9))
                nom = float(round(df.close.iloc[-1] - df.close.min(), 9))
                den = float(df.close.max() - df.close.min())
                nom = float(df.close.iloc[-1] - df.close.min())

                if den == 0:
                    value = 0
                else:
                    value = nom / den
                return value

            screen_data.append(
                {
                    "symbol": symbol,
                    "n2m": df_2m.close.nunique(),
                    "c2m": self._get_ask_bid_price_changes(df_2m),
                    "n1m": df_1m.close.nunique(),
                    "c1m": self._get_ask_bid_price_changes(df_1m),
                    "n7d": df_1w.close.nunique(),
                    "c7d": self._get_ask_bid_price_changes(df_1w),
                    "n1d": df_1d.close.nunique(),
                    "n3h": df_3h.close.nunique(),
                    "diff": susc_perc,
                    "last_1d_vol": prev_df_1d.volumes.sum(),
                    "1d_vol": df_1d.volumes.sum(),
                    "2m_lvl": get_value(df_2m) * 100,
                    "1m_lvl": get_value(df_1m) * 100,
                    "7d_lvl": get_value(df_1w) * 100,
                    "1d_lvl": get_value(df_1d) * 100,
                    "ask": pair.ask_price,
                    "bid": pair.bid_price,
                    "ask_q": int(pair.ask_quantity),
                    "bid_q": int(pair.bid_quantity),
                    "b/a": pair.bid_quantity / pair.ask_quantity,
                    "fill ask": df_1d.volumes.sum() / float(pair.ask_quantity),
                    "fill bid": df_1d.volumes.sum() / float(pair.bid_quantity),
                }
            )

        screen_result = DataFrame(screen_data)
        screen_result.set_index("symbol", inplace=True)

        return screen_result

    async def show(self, symbol):
        start_datetime_5mn = datetime.now() - timedelta(hours=48)
        start_datetime_1h = datetime.now() - timedelta(days=60)
        end_datetime = datetime.now()

        df_5mn, df_1h = await asyncio.gather(
            self.controllers.binance.get_klines(
                symbol, interval="5m", start_datetime=start_datetime_5mn, end_datetime=end_datetime
            ),
            self.controllers.binance.get_klines(
                symbol, interval="1h", start_datetime=start_datetime_1h, end_datetime=end_datetime
            ),
        )

        _, axes = plt.subplots(nrows=2, ncols=3, figsize=(33, 7))

        axes[0][0].plot(df_1h.close)
        axes[0][0].set_title("60 days close")

        axes[0][1].plot(df_1h.close[end_datetime - timedelta(days=30):])
        axes[0][1].set_title("30 days close")

        axes[0][2].plot(df_1h.close[end_datetime - timedelta(days=7):])
        axes[0][2].set_title("7 days close")

        axes[1][0].plot(df_5mn.close)
        axes[1][0].set_title("48 hours close")

        axes[1][1].plot(df_5mn.close[end_datetime - timedelta(hours=12):])
        axes[1][1].set_title("12 hours close")

        axes[1][2].plot(df_1h.volumes[end_datetime - timedelta(days=7):])
        axes[1][2].set_title("7 days vol")

        plt.tight_layout()

        plt.show()

        return df_5mn, df_1h
