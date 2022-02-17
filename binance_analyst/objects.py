from __future__ import annotations

from dataclasses import field
from typing import Dict

from pydantic import BaseModel, Field


class Coin(BaseModel):
    name: str

    def to(self, coin: Coin) -> Pair:
        return Pair(self, coin)


class CoinAmount(BaseModel):
    coin: Coin
    amount: float = 0.0


class Pair(BaseModel):
    base: Coin
    quote: Coin

    @property
    def symbol(self):
        return self.base.name + self.quote.name


class Account(BaseModel):
    coins: Dict[str, CoinAmount] = Field(default_factory=dict)
