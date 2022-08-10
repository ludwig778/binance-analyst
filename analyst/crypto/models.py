from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class CoinAmount(BaseModel):
    coin: str
    amount: float = 0.0


class Pair(BaseModel):
    base: str
    quote: str
    quote_min_amount: float

    @property
    def symbol(self):
        return self.base + self.quote

    def revert(self):
        return Pair(base=self.quote, quote=self.base, quote_min_amount=1 / self.quote_min_amount)


class PairPrices(BaseModel):
    ask: float = Field(alias="askPrice")
    bid: float = Field(alias="bidPrice")
    ask_quantity: float = Field(alias="askQty")
    bid_quantity: float = Field(alias="bidQty")


Account = Dict[str, CoinAmount]
Pairs = Dict[str, Pair]
PairsPrices = Dict[str, PairPrices]


class BinanceInfos(BaseModel):
    account: Account
    pairs: Pairs
    prices: PairsPrices
