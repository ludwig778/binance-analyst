import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional, Set

from numpy import inf, nan
from pandas import DataFrame, concat, to_datetime

from analyst.adapters.factory import Adapters
from analyst.crypto.exceptions import InvalidPairCoins
from analyst.crypto.models import (
    Account,
    BinanceSummary,
    CoinAmount,
    Pair,
    PairPrices,
    Pairs,
    PairsPrices,
)
from analyst.logging import getLogger

logger = getLogger(__name__)


class BinanceController:
    def __init__(self, adapters: Adapters):
        self.adapters = adapters

    def load_account(self) -> Account:
        account_info = self.adapters.binance.get_account_info()

        coins = {}
        for coin in account_info.get("balances"):
            amount = float(coin.get("free", 0))

            if amount:
                name = coin.get("asset")

                if name.startswith("LD"):
                    name = name.replace("LD", "")
                    continue

                coins[name] = CoinAmount(coin=name, amount=amount)

        return coins

    def load_exchange_data(self) -> Pairs:
        exchange_data = {}

        for coin_data in self.adapters.binance.get_exchange_info()["symbols"]:
            symbol = coin_data.get("symbol")

            base_coin = coin_data.get("baseAsset")
            quote_coin = coin_data.get("quoteAsset")

            filters = {filter["filterType"]: filter for filter in coin_data.get("filters")}
            quote_min_amount = float(filters["MIN_NOTIONAL"]["minNotional"])

            exchange_data[symbol] = Pair(
                base=base_coin, quote=quote_coin, quote_min_amount=quote_min_amount
            )

        return exchange_data

    def load_prices(self) -> PairsPrices:
        return {
            prices_data.get("symbol"): PairPrices(**prices_data)
            for prices_data in self.adapters.binance.get_prices()
        }

    def load_summary(self) -> BinanceSummary:
        account = self.load_account()
        pairs = self.load_exchange_data()
        prices = self.load_prices()

        return BinanceSummary(account=account, pairs=pairs, prices=prices)

    @staticmethod
    def filter_pairs(pairs: Pairs, coin_strs: List[str], exclusive=False) -> Pairs:
        op = operator.__and__ if exclusive else operator.__or__

        return {
            symbol: pair
            for symbol, pair in pairs.items()
            if op(pair.base in coin_strs, pair.quote in coin_strs)
        }

    def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        start_datetime: datetime = datetime(2000, 1, 1),
        end_datetime: datetime = datetime.now(),
    ) -> DataFrame:
        df = self.adapters.binance.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        # Fix, trades are integers
        if not df.empty:
            df = df.replace([inf, -inf], nan).dropna()
            df["trades"] = df["trades"].astype(int)

        return df

    def load_dataframes(self, pairs: Pairs, workers=5, **kwargs) -> DataFrame:
        logger.debug(f"Fetching {len(pairs)} pairs...")
        start_time = datetime.now()

        dataframes = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.get_klines, pair.symbol, **kwargs): symbol
                for symbol, pair in pairs.items()
            }
            for future in as_completed(futures):
                symbol = futures[future]
                dataframes[symbol] = future.result()

        dataframe = concat(dataframes, join="outer", axis=1)
        dataframe.index = to_datetime(dataframe.index)

        logger.debug(f"Fetching pairs took {(datetime.now() - start_time).total_seconds():.2f} secs")

        return dataframe

    def convert_coin(
        self, asset: CoinAmount, to: str, exchange_prices: Optional[PairsPrices] = None
    ) -> CoinAmount:

        if exchange_prices is None:
            exchange_prices = self.load_prices()

        if price := exchange_prices.get(f"{asset.coin}{to}"):
            return CoinAmount(coin=to, amount=asset.amount * price.ask)
        elif price := exchange_prices.get(f"{to}{asset.coin}"):
            return CoinAmount(coin=to, amount=asset.amount / price.bid)
        else:
            raise InvalidPairCoins(f"{asset.coin}-{to}")

    def get_transitional_coins(
        self, origin: str, dest: str, exchange_prices: Optional[PairsPrices] = None
    ) -> Set[str]:

        if exchange_prices is None:
            exchange_prices = self.load_prices()

        origin_candidates = set()
        dest_candidates = set()

        for symbol in exchange_prices.keys():
            if origin in symbol:
                origin_candidates.add(symbol.replace(origin, ""))
            elif dest in symbol:
                dest_candidates.add(symbol.replace(dest, ""))

        return origin_candidates.intersection(dest_candidates)

    def convert_account_coins_to(self, account: Account, to: str) -> CoinAmount:
        total = CoinAmount(coin=to, amount=0.0)

        for asset in account.values():
            if asset.coin == to:
                total.amount += asset.amount

            else:
                try:
                    converted = self.convert_coin(asset, to)
                except InvalidPairCoins:
                    transitions = self.get_transitional_coins(asset.coin, to)

                    transition_results = {}
                    for transition in transitions:
                        converted = self.convert_coin(self.convert_coin(asset, transition), to)
                        transition_results[transition] = converted

                    converted = sorted(transition_results.values(), key=lambda x: x.amount)[-1]

                total.amount += converted.amount

        return total
