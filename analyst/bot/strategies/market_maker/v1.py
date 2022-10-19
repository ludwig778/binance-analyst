# type: ignore

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from pprint import pprint
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from numpy import log

from analyst.bot.exceptions import StrategyExit
from analyst.bot.order_manager import PairSide, Side
from analyst.bot.strategies.base import Strategy, StrategyFlags
from analyst.crypto.models import MarketStreamTicker, Order
from analyst.utils import trunk_uuid

if TYPE_CHECKING:
    from analyst.bot.order_manager import OrderManager

logger = getLogger("file")


class MarketMakerV1(Strategy):
    name = "market_maker"
    version = "v1"

    class Flags(StrategyFlags):
        price_going_down = ()
        insufficient_fund = ()

    def __init__(
        self,
        symbol: str,
        quote_quantity: Decimal,
        internal_order_id: Optional[int] = None,
        converted_base_quantity: Decimal = Decimal(),
        **kwargs,
    ):
        super(MarketMakerV1, self).__init__(**kwargs)

        self.symbol = symbol
        self.quote_quantity = quote_quantity
        self.internal_order_id = internal_order_id
        self.converted_base_quantity = converted_base_quantity

        self._last_ticker_data: Optional[MarketStreamTicker] = None
        self._last_update: Optional[datetime] = None

        self._threshold_limit = log(8)
        self._threshold_release = log(4)

    async def setup(self, order_manager):
        logger.info(f"setup strategy_id={trunk_uuid(self.id)}")

        if self.internal_order_id:
            await order_manager.setup_order(self.internal_order_id)

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "key": self.get_key(),
            "args": {
                "symbol": self.symbol,
                "quote_quantity": self.quote_quantity,
                "internal_order_id": self.internal_order_id,
                "converted_base_quantity": self.converted_base_quantity,
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "flags": self.flags,
            "state": self.state,
        }

    @classmethod
    def create(
        cls,
        quote_quantity,
        internal_order_id: Optional[UUID] = None,
        converted_base_quantity: Decimal = Decimal(),
        **kwargs,
    ):
        if not isinstance(quote_quantity, Decimal):
            quote_quantity = Decimal(quote_quantity)

        if internal_order_id and not isinstance(internal_order_id, UUID):
            internal_order_id = UUID(internal_order_id)

        if converted_base_quantity and not isinstance(converted_base_quantity, Decimal):
            converted_base_quantity = Decimal(converted_base_quantity)

        return super().post_create(
            quote_quantity=quote_quantity,
            internal_order_id=internal_order_id,
            converted_base_quantity=converted_base_quantity,
            **kwargs,
        )

    @staticmethod
    def get_args_meta():
        return {"symbol": str, "quote_quantity": float}

    def get_default_flags(self):
        return self.Flags.no_flags

    def get_key(self):
        return f"{self.symbol}:{self.quote_quantity}"

    def to_str(self):
        return f"{self.name}:{self.version} on {self.symbol}"

    def get_stream_names(self) -> List[str]:
        return [f"{self.symbol.lower()}@ticker"]

    def gatekeeping(self, order_manager: OrderManager):
        try:
            pair = order_manager.get_pair(self.symbol)
        except KeyError:
            raise Exception(f"Pair {self.symbol} does not exist strategy_id={trunk_uuid(self.id)}")

        if not order_manager.has_sufficient_quantity(pair, self.quote_quantity, PairSide.quote):
            raise Exception(f"Insufficient funds strategy_id={trunk_uuid(self.id)}")

    def details(self, *args, **kwargs):
        dt_obj = datetime.now()
        logger.info(
            dt_obj.strftime("%H:%M:%S"),
            f"{str(hex(id(self)))} {self.get_key()}",
            *args,
            f"{self.converted_base_quantity} {str(self.internal_order_id)}",
            **kwargs,
        )

    async def set_flags(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        quantity_balance = log(float(ticker_data.ask_quantity / ticker_data.bid_quantity))

        if self.Flags.price_going_down not in self.flags and quantity_balance >= self._threshold_limit:
            logger.debug("flags: price going down triggered")

            self.flags |= self.Flags.price_going_down

            await order_manager.controllers.mongo.store_strategy(self)

        elif self.Flags.price_going_down in self.flags and quantity_balance <= self._threshold_release:
            logger.debug("flags: price going down released")

            self.flags -= self.Flags.price_going_down

            await order_manager.controllers.mongo.store_strategy(self)

    async def process_ticker_data(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        if self._last_ticker_data:
            ask_went_down = ticker_data.ask_price < self._last_ticker_data.ask_price
            # bid_went_up = ticker_data.bid_price > self._last_ticker_data.bid_price
        else:
            ask_went_down = False
            # bid_went_up = False

        await self.set_flags(ticker_data, order_manager)

        order = order_manager.get_order(self.internal_order_id)
        pair = order_manager.get_pair(ticker_data.symbol)

        # NO PENDING ORDER, NO FLAGS, NO CONVERTED
        if (
            (not order or order and order.is_closed())
            and self.Flags.price_going_down not in self.flags
            and not self.converted_base_quantity
        ):
            logger.info("initiating order")

            if not order_manager.has_sufficient_quantity(pair, self.quote_quantity, PairSide.quote):
                logger.info("initiating order: unsufficient funds")
                raise Exception(f"Insufficient funds strategy_id={trunk_uuid(self.id)}")

                await self.stop(order_manager)

                self.internal_order_id = None
                self.flags |= self.Flags.insufficient_fund

                await order_manager.controllers.mongo.store_strategy(self)

                self.log_ticker(ticker_data, "Stopping: Insufficient fund4", label="STOP")

                raise StrategyExit()

            price = ticker_data.bid_price
            base_quantity = order_manager.floor_base_quantity(
                order_manager.get_pair(ticker_data.symbol),
                order_manager.convert_to_base_quantity(self.quote_quantity, price),
            )

            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.buy,
                price=price,
                quantity=base_quantity,
                market_making=True,
                strategy=self,
            )

            self.internal_order_id = order.internal_id

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Buy", label="POSITION")

            self.details("initiating order: out")

        # WOT
        elif (not order or order and order.is_closed()) and self.converted_base_quantity:
            self.details("initiating sell order")
            print(order, self.flags, self.converted_base_quantity)

            """
            if not self.has_sufficient_funds(order_manager, ticker_data.symbol, self.quantity):
                print("======", hex(id(self)), self.get_key(), 6)
                await self.stop(order_manager)

                self.internal_order_id = None
                self.flags |= self.Flags.insufficient_fund

                await order_manager.controllers.mongo.store_strategy(self)

                self.log_ticker(ticker_data, "Stopping: Insufficient fund5", label="STOP")

                raise StrategyExit()
            """
            print(self.converted_base_quantity)
            print(bool(self.converted_base_quantity))
            pprint(order_manager.account)
            await asyncio.sleep(1)
            pprint(order_manager.account)

            base_quantity = self.converted_base_quantity * Decimal("0.999")
            print(f"{base_quantity=}")
            pair = order_manager.get_pair(ticker_data.symbol)
            base_quantity = order_manager.floor_base(pair, base_quantity)
            print(f"floored {base_quantity=}")

            if not base_quantity:
                self.details("initiating sell order: unsufficient funds")
                await self.stop(order_manager)

                self.internal_order_id = None
                self.flags |= self.Flags.insufficient_fund

                await order_manager.controllers.mongo.store_strategy(self)

                self.log_ticker(ticker_data, "Stopping: Insufficient fund1", label="STOP")

                raise StrategyExit()

            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.sell,
                price=ticker_data.ask_price,
                quantity=base_quantity,
                market_making=True,
                strategy=self,
            )
            self.internal_order_id = order.internal_id

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Sell", label="POSITION")

            self.details("initiating sell order: out")

        # If Prices changed, ORDER OPEN, move lower if selling, higher if buying
        # NO PENDING ORDER, NO FLAGS, NO CONVERTED
        elif (order and order.is_open() and order.side == "SELL") and (
            (ask_went_down and ticker_data.ask_price != order.price)
            or (self.Flags.price_going_down in self.flags and ticker_data.ask_price == order.price)
        ):
            self.details("ask_went_down")
            pprint(order.dict())
            print(f"{ask_went_down=}")
            cancelled_order = await order_manager.cancel_order(order, self)
            pair = order_manager.get_pair(order.symbol)

            base_quantity = cancelled_order.requested_quantity - cancelled_order.executed_quantity

            if ask_went_down:
                price = ticker_data.ask_price
            else:
                price = order.price - pair.base_asset_atom_quantity

            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.sell,
                price=price,
                quantity=base_quantity,
                market_making=True,
                strategy=self,
            )

            self.internal_order_id = order.internal_id
            self.converted_base_quantity = base_quantity

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Sell lower", label="POSITION")

            self.details("ask_went_down: out")

        elif (
            order
            and order.is_open()
            and order.side == "BUY"
            and (
                order.price > ticker_data.bid_price
                or (order.price < ticker_data.bid_price and self.Flags.price_going_down not in self.flags)
            )
        ):
            self.details("price_went_down")
            pprint(order.dict())
            print(self.flags)
            pprint(ticker_data.dict())
            cancelled_order = await order_manager.cancel_order(order, self)

            quantity = self.quantity - cancelled_order.executed_quantity

            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.buy,
                price=ticker_data.bid_price,
                quantity=quantity,
                market_making=True,
                strategy=self,
            )
            self.internal_order_id = order.internal_id
            self.converted_base_quantity = cancelled_order.executed_quantity

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Buy higher", label="POSITION")

            self.details("price_going_down: out")

        # If BUYING, STOPPING state and no executed quantity
        elif self.is_stopping and order.side == "BUY" and order.executed_quantity == Decimal("0.0"):
            self.details("stopping clean")
            pprint(order.dict())

            await order_manager.cancel_order(order, self)

            await self.stop(order_manager)

            self.internal_order_id = None

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Cancelling buy and stopping", label="STOP")

            self.details("stopping clean: out")

            raise StrategyExit()

        # If BUYING, PRICES NO CHANGED, prices going down flag
        elif (
            order
            and self.Flags.price_going_down in self.flags
            and order.side == "BUY"
            and order.price == ticker_data.bid_price
        ):
            self.details("buy lower or neutral")
            logger.debug(order.dict())
            logger.debug(self.flags)
            cancelled_order = await order_manager.cancel_order(order, self)
            logger.debug("CANCELED " * 123)
            logger.debug(cancelled_order.dict())

            if order.executed_quantity:
                self.details("buy lower or neutral: canceled and sell back")
                order = await order_manager.create_order(
                    symbol=self.symbol,
                    side=Side.sell,
                    price=cancelled_order.price,
                    quantity=cancelled_order.executed_quantity,
                    market_making=True,
                    strategy=self,
                )

                self.internal_order_id = order.internal_id
                self.converted_base_quantity = cancelled_order.executed_quantity

                # self.log_order(order, "Sell back for flag", label="POSITION")
            else:
                self.details("buy lower or neutral: canceled clean")
                self.internal_order_id = None
                # ADDED LAST
                self.converted_base_quantity = Decimal()

                # self.log_order(order, "Cancel and wait for flag release", label="NEUTRAL")

            await order_manager.controllers.mongo.store_strategy(self)

            self.details("buy lower or neutral: out")

        self._last_ticker_data = ticker_data
        self._last_update = datetime.now()

    async def process_order(self, order: Order, order_manager: OrderManager):
        self.details("process order")

        if not order.is_filled():
            self.details("process order: not filled")
            # pprint(order.dict())
            return order

        await asyncio.sleep(0.5)

        # self.log_order(order, f"{order.side.capitalize()} Filled")

        if order.side == "BUY":
            self.details("process order: sell")
            self.converted_base_quantity = order.executed_quantity

            print(f"{order.executed_quantity}")
            pprint(order_manager.account)
            # await asyncio.sleep(1)
            pprint(order_manager.account)

            quantity = self.converted_base_quantity * Decimal("0.999")
            print(f"{quantity=}")
            pair = order_manager.get_pair(order.symbol)
            quantity = order_manager.floor_base(pair, quantity)
            print(f"floored {quantity=}")

            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.sell,
                price=self._last_ticker_data.ask_price,
                quantity=quantity,
                market_making=True,
                strategy=self,
            )
            self.internal_order_id = order.internal_id

            await order_manager.controllers.mongo.store_strategy(self)

            # self.log_order(order, "Buy => Sell", label="POSITION")

            self.details("process order: sell: out")

            return order

        elif order.side == "SELL":
            self.details("process order: buy")
            self.internal_order_id = None
            self.converted_base_quantity = Decimal()

            self.details("process order: sleep 1")
            # pprint(order_manager.account)
            await asyncio.sleep(3)
            # pprint(order_manager.account)
            self.details("process order: sleep 2")

            """
            if self.Flags.price_going_down in self.flags:
                self.details("process order: price going doing flag = neutral")
                await order_manager.controllers.mongo.store_strategy(self)

                self.log_order(order, "Wait for flag release", label="NEUTRAL")

                self.details("process order: price going doing flag = neutral: out")
                return

            if not self.has_sufficient_funds(order_manager, order.symbol, self.quantity):
                self.details("process order: insufficient fund")
                await self.stop(order_manager)

                self.internal_order_id = None
                self.flags |= self.Flags.insufficient_fund

                await order_manager.controllers.mongo.store_strategy(self)

                self.log_order(order, "Stopping: Insufficient fund2", label="STOP")

                self.details("process order: insufficient fund: out")

                raise StrategyExit()
            """

            if self.is_stopping:
                self.details("process order: is stopping")
                await self.stop(order_manager)

                await order_manager.controllers.mongo.store_strategy(self)

                # self.log_order(order, "Stopping", label="STOP")

                self.details("process order: is stopping: out")

                raise StrategyExit()

            """
            order = await order_manager.create_order(
                symbol=self.symbol,
                side=Side.buy,
                price=self._last_ticker_data.bid_price,
                quantity=self.quantity,
                market_making=True,
                strategy=self
            )
            self.internal_order_id = order.internal_id

            await order_manager.controllers.mongo.store_strategy(self)

            self.log_order(order, "Sell => Buy", label="POSITION")

            self.details("process order: buy: out")

            return order
            """
