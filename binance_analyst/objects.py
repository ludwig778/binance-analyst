from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class Coin(BaseModel):
    name: str

    def to(self, other: Coin) -> Pair:
        return Pair(base=self, quote=other)


class CoinAmount(BaseModel):
    coin: Coin
    amount: float = 0.0


class Pair(BaseModel):
    base: Coin
    quote: Coin

    @property
    def symbol(self):
        return self.base.name + self.quote.name

    def revert(self):
        return Pair(base=self.quote, quote=self.base)


class Account(BaseModel):
    coins: Dict[str, CoinAmount] = Field(default_factory=dict)
