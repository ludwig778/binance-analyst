from typing import Optional

from cachetools import TTLCache, cached

from binance_analyst.adapters.binance import TickerPrices
from binance_analyst.objects import Coin, CoinAmount, Pair
from binance_analyst.repositories.base import AdaptersAwareRepository


class ExchangeRepository(AdaptersAwareRepository):
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
            raise Exception(f"No ticker found for coins {asset.coin.name} {to.name}")
