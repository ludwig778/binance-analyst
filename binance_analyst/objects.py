from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(unsafe_hash=True)
class Coin:
    name: str

    def to(self, coin: Coin) -> Pair:
        return Pair(self, coin)


@dataclass(unsafe_hash=True)
class CoinAmount:
    coin: Coin
    amount: float = 0.0


@dataclass(unsafe_hash=True)
class Pair:
    base: Coin
    quote: Coin

    @property
    def symbol(self):
        return self.base.name + self.quote.name


@dataclass
class Account:
    coins: Dict[str, CoinAmount] = field(default_factory=dict)
