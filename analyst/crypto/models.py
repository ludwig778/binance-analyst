from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, root_validator


class CoinAmount(BaseModel):
    coin: str
    quantity: Decimal = Field(default_factory=Decimal)


class Pair(BaseModel):
    base: str
    quote: str
    quote_min_amount: Decimal

    base_asset_precision: int
    quote_asset_precision: int

    min_quantity: Decimal
    max_quantity: Decimal
    step_size: Decimal

    ask_price: Decimal
    bid_price: Decimal

    ask_quantity: Decimal
    bid_quantity: Decimal

    class Config:
        json_encoders = {Decimal: float}

    def __hash__(self):
        return hash(self.symbol)

    @property
    def symbol(self):
        return self.base + self.quote

    def has_ask_bid_prices_changed(self, other: Pair) -> bool:
        return self.ask_price != other.ask_price or self.bid_price != other.bid_price

    @property
    def base_min_quantity(self):
        return round(
            (self.quote_min_amount / self.ask_price // self.step_size) * self.step_size,
            self.base_asset_precision,
        )

    @property
    def base_asset_atom_quantity(self):
        return Decimal(f"1e-{self.base_asset_precision}")


Account = Dict[str, CoinAmount]
Pairs = Dict[str, Pair]


class Order(BaseModel):
    id: int = Field(alias="orderId")
    symbol: str
    status: str
    type: str
    side: str

    price: Decimal = Field(alias="price")
    stop_price: Decimal = Field(alias="stopPrice")

    time_in_force: str = Field(alias="timeInForce")

    requested_quantity: Decimal = Field(alias="origQty")
    executed_quantity: Decimal = Field(alias="executedQty")

    created_at: datetime = Field(alias="time")
    updated_at: datetime = Field(alias="updateTime")

    strategy_id: Optional[UUID] = None
    internal_id: UUID = Field(alias="internal_id", default_factory=uuid4)

    class Config:
        allow_population_by_field_name = True

    @classmethod
    def create(cls, **kwargs):
        kwargs.setdefault("stop_price", 0.0)
        kwargs.setdefault("time_in_force", "GTC")
        kwargs.setdefault("executed_quantity", 0.0)

        kwargs.setdefault("created_at", datetime.now())
        kwargs.setdefault("updated_at", datetime.now())

        return cls(**kwargs)

    @root_validator
    def remove_timestamps_timezone(cls, values):
        values["created_at"] = values["created_at"].replace(tzinfo=None)
        values["updated_at"] = values["updated_at"].replace(tzinfo=None)

        return values

    def is_open(self):
        return self.status in ("NEW", "PARTIALLY_FILLED")

    def is_closed(self):
        return not self.is_open()

    def is_filled(self):
        return self.status == "FILLED"

    def is_cancelled(self):
        return not self.is_open() and not self.is_filled()

    def filled_at(self):
        return self.executed_quantity / self.requested_quantity * 100

    def filled_quote_quantity(self):
        return self.executed_quantity * self.price

    @property
    def rest_to_be_filled_quantity(self):
        return self.requested_quantity - self.executed_quantity


class OrderFromUserDataStream(Order):
    id: int = Field(alias="i")
    symbol: str = Field(alias="s")
    status: str = Field(alias="X")
    type: str = Field(alias="o")
    side: str = Field(alias="S")

    price: Decimal = Field(alias="p")
    stop_price: Decimal = Field(alias="P")

    time_in_force: str = Field(alias="f")

    requested_quantity: Decimal = Field(alias="q")
    executed_quantity: Decimal = Field(alias="l")

    created_at: datetime = Field(alias="O")
    updated_at: datetime = Field(alias="E")


class OutboundAccountBalance(BaseModel):
    coin: str = Field(alias="a")
    free: Decimal = Field(alias="f")
    locked: Decimal = Field(alias="l")

    class Config:
        allow_population_by_field_name = True


class OutboundAccountPosition(BaseModel):
    updated_at: datetime = Field(alias="u")

    balances: List[OutboundAccountBalance] = Field(alias="B")

    @root_validator
    def remove_timestamp_timezone(cls, values):
        values["updated_at"] = values["updated_at"].replace(tzinfo=None)

        return values

    class Config:
        allow_population_by_field_name = True


class Position(BaseModel):
    opened_order: Order
    closed_order: Optional[Order] = None


class MarketStreamTicker(BaseModel):
    timestamp: datetime = Field(alias="E", default_factory=datetime.now)
    symbol: str = Field(alias="s")
    last_price: Decimal = Field(alias="c")
    ask_price: Decimal = Field(alias="a")
    ask_quantity: Decimal = Field(alias="A")
    bid_price: Decimal = Field(alias="b")
    bid_quantity: Decimal = Field(alias="B")
    trades: int = Field(alias="n")

    class Config:
        allow_population_by_field_name = True

    """
    @classmethod
    def create(cls, **kwargs):
        kwargs.setdefault("stop_price", 0.0)
        kwargs.setdefault("time_in_force", "GTC")
        kwargs.setdefault("executed_quantity", 0.0)

        kwargs.setdefault("created_at", datetime.now())
        kwargs.setdefault("updated_at", datetime.now())

        return cls(**kwargs)
    """

    def has_ask_bid_prices_changed(self, other: MarketStreamTicker) -> bool:
        return (
            # self.last_price != other.last_price or
            self.ask_price != other.ask_price
            or self.bid_price != other.bid_price
        )

    @root_validator
    def remove_timestamp_timezone(cls, values):
        values["timestamp"] = values["timestamp"].replace(tzinfo=None)

        return values


class TradeStreamObject(BaseModel):
    id: int = Field(alias="t")
    price: Decimal = Field(alias="p")
    quantity: Decimal = Field(alias="q")
    market_maker: bool = Field(alias="m")
    buyer: int = Field(alias="b")
    seller: int = Field(alias="a")


"""
    {
        "e": "trade",     // Event type
        "E": 123456789,   // Event time
        "s": "BNBBTC",    // Symbol
        "t": 12345,       // Trade ID
        "p": "0.001",     // Price
        "q": "100",       // Quantity
        "b": 88,          // Buyer order ID
        "a": 50,          // Seller order ID
        "T": 123456785,   // Trade time
        "m": true,        // Is the buyer the market maker?
        "M": true         // Ignore
    }
"""
