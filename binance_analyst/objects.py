from __future__ import annotations

from typing import Dict

from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass(unsafe_hash=True)
class Coin:
    name: str

    def to(self, other: Coin) -> Pair:
        return Pair(base=self, quote=other)


@dataclass
class CoinAmount:
    coin: Coin
    amount: float = 0.0


@dataclass
class Pair:
    base: Coin
    quote: Coin

    @property
    def symbol(self):
        return self.base.name + self.quote.name

    def revert(self):
        return Pair(base=self.quote, quote=self.base)


@dataclass
class Account:
    coins: Dict[str, CoinAmount] = Field(default_factory=dict)
