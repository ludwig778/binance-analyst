from typing import Optional, Set

from cachetools import TTLCache, cached

from binance_analyst.adapters.binance import TickerPrices
from binance_analyst.exceptions import InvalidPairCoins
from binance_analyst.models import Coin, CoinAmount, Pair
from binance_analyst.controllers.base import AdaptersAwareController


class ExchangeController(AdaptersAwareController):
    @cached(cache=TTLCache(maxsize=1, ttl=45))
    def load(self):
        return self.adapters.binance.get_prices()

    def convert(
        self, asset: CoinAmount, to: Coin, exchange_prices: Optional[TickerPrices] = None
    ) -> CoinAmount:

        if exchange_prices is None:
            exchange_prices = self.load()

        pair = Pair(base=asset.coin, quote=to)

        if price := exchange_prices.prices.get(pair.symbol):
            return CoinAmount(coin=to, amount=asset.amount * price.bid)
        elif price := exchange_prices.prices.get(pair.revert().symbol):
            return CoinAmount(coin=to, amount=asset.amount / price.ask)
        else:
            raise InvalidPairCoins(f"{asset.coin.name}-{to.name}")

    def get_transitional_coins(
        self, origin: Coin, dest: Coin, exchange_prices: Optional[TickerPrices] = None
    ) -> Set[Coin]:

        if exchange_prices is None:
            exchange_prices = self.load()

        coins = set()
        candidates = set()

        for symbol in exchange_prices.prices.keys():
            if origin.name in symbol:
                candidates.add(symbol.replace(origin.name, ""))

        for symbol in exchange_prices.prices.keys():
            if dest.name in symbol:
                coin_name = symbol.replace(dest.name, "")
                if coin_name in candidates:
                    coins.add(Coin(name=coin_name))

        return coins
