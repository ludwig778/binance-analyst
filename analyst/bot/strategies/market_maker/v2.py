# type: ignore

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from logging import getLogger
from pprint import pprint
from typing import TYPE_CHECKING, List, Optional, Set
from uuid import UUID

from analyst.bot.exceptions import StrategyExit
from analyst.bot.order_manager import Side
from analyst.bot.strategies.base import Strategy, StrategyFlags
from analyst.crypto.exceptions import OrderWouldMatch
from analyst.crypto.models import MarketStreamTicker, Order
from analyst.utils import trunk_uuid

if TYPE_CHECKING:
    from analyst.bot.order_manager import OrderManager

logger = getLogger("file")


class MarketMakerV2(Strategy):
    name = "market_maker"
    version = "v2"

    class Flags(StrategyFlags):
        insufficient_fund = ()

    def __init__(
        self,
        symbol: str,
        quote_quantity: Decimal,
        internal_buy_order_ids: Set[int],
        internal_sell_order_ids: Set[int],
        max_buy_orders: int = 2,
        max_increase_step: int = 6,
        max_increase_retain_delta: timedelta = timedelta(days=1),
        **kwargs,
    ):
        super(MarketMakerV2, self).__init__(**kwargs)

        self.symbol = symbol
        self.quote_quantity = quote_quantity
        self.internal_buy_order_ids = internal_buy_order_ids
        self.internal_sell_order_ids = internal_sell_order_ids

        self.max_buy_orders = max_buy_orders
        self.max_increase_step = max_increase_step
        self.max_increase_retain_delta = max_increase_retain_delta

        self._last_ticker_data: Optional[MarketStreamTicker] = None
        self._last_update: Optional[datetime] = None

        self._last_price_timestamps = {}

    async def setup(self, order_manager):
        self.details("setup")

        changed = False

        for internal_order_id in list(self.internal_buy_order_ids):
            order = await order_manager.setup_order(internal_order_id)

            if order.status == "FILLED":
                changed = True
                self.internal_buy_order_ids.remove(internal_order_id)

        for internal_order_id in list(self.internal_sell_order_ids):
            order = await order_manager.setup_order(internal_order_id)

            if order.status == "FILLED":
                changed = True
                self.internal_sell_order_ids.remove(internal_order_id)

        if changed:
            await order_manager.controllers.mongo.store_strategy(self)

        self.details("setup: out")

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "key": self.get_key(),
            "args": {
                "symbol": self.symbol,
                "quote_quantity": self.quote_quantity,
                "internal_buy_order_ids": self.internal_buy_order_ids,
                "internal_sell_order_ids": self.internal_sell_order_ids,
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
        internal_buy_order_ids: Optional[List[UUID]] = None,
        internal_sell_order_ids: Optional[List[UUID]] = None,
        **kwargs,
    ):
        if not isinstance(quote_quantity, Decimal):
            quote_quantity = Decimal(quote_quantity)

        if internal_buy_order_ids:
            internal_buy_order_ids = set(internal_buy_order_ids)
        else:
            internal_buy_order_ids = set()

        if internal_sell_order_ids:
            internal_sell_order_ids = set(internal_sell_order_ids)
        else:
            internal_sell_order_ids = set()

        return super().post_create(
            quote_quantity=quote_quantity,
            internal_buy_order_ids=internal_buy_order_ids,
            internal_sell_order_ids=internal_sell_order_ids,
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
            order_manager.get_pair(self.symbol)
        except KeyError:
            raise Exception(f"Pair {self.symbol} does not exist strategy_id={trunk_uuid(self.id)}")

        if not self.has_sufficient_funds(order_manager, self.symbol, self.quote_quantity):
            raise Exception("Insufficient funds")

    def details(self, *args, **kwargs):
        dt_obj = datetime.now()
        logger.info(
            dt_obj.strftime("%H:%M:%S"),
            f"{str(hex(id(self)))} {self.get_key()}",
            *args,
            f"{len(self.internal_buy_order_ids)}",
            f"{len(self.internal_sell_order_ids)}",
            **kwargs,
        )

    def get_buy_orders(self, order_manager):
        orders = {}

        for internal_order_id in self.internal_buy_order_ids:

            order = order_manager.get_order(internal_order_id)
            if order:
                orders[order.price] = order

        return orders

    def get_sell_orders(self, order_manager):
        orders = defaultdict(list)

        for internal_order_id in self.internal_sell_order_ids:
            order = order_manager.get_order(internal_order_id)
            if order:
                orders[order.price].append(order)

        return orders

    async def update_buy_side(self, order_manager: OrderManager, bid_price: Decimal):
        buy_orders = self.get_buy_orders(order_manager)
        sell_orders = self.get_sell_orders(order_manager)

        pair = order_manager.get_pair(self.symbol)
        atom = pair.base_asset_atom_quantity

        converted_base_quantity = Decimal()

        for atom_index in range(self.max_buy_orders):
            price = bid_price - (atom_index * atom)
            order = buy_orders.get(price)

            if atom_index == 0 and len(sell_orders.get(price + atom, ())) >= 1:
                continue

            base_quantity = order_manager.convert_to_base_quantity(self.quote_quantity, price)
            base_quantity = order_manager.floor_base_quantity(pair, base_quantity)

            if order and order.requested_quantity != base_quantity:
                cancelled_order = await order_manager.cancel_order(order, self)

                if cancelled_order.executed_quantity:
                    # print(f"{cancelled_order.executed_quantity=}")
                    converted_base_quantity += cancelled_order.executed_quantity

                del buy_orders[cancelled_order.price]
                self.internal_buy_order_ids.remove(order.internal_id)

                self.details(f"Cancel order @ {price:f} => {str(order.internal_id)[:8]}")

                order = None

            if not order:
                try:
                    order = await order_manager.create_order(
                        symbol=self.symbol,
                        side=Side.buy,
                        price=price,
                        quantity=base_quantity,
                        market_making=True,
                        strategy=self,
                    )
                except OrderWouldMatch:
                    self.details(f"Created order aborted @ {price:f}: would match")

                    continue

                buy_orders[order.price] = order

                self.internal_buy_order_ids.add(order.internal_id)

                await order_manager.controllers.mongo.store_strategy(self)

                self.details(f"Created order @ {price:f} => {str(order.internal_id)[:8]}")

        # Cancel buy order above BID PRICE (already filled?)
        for order_price, order in list(buy_orders.items()):
            if order_price > bid_price:
                cancelled_order = await order_manager.cancel_order(order, self)

                if cancelled_order.executed_quantity:
                    converted_base_quantity += cancelled_order.executed_quantity

                self.internal_buy_order_ids.remove(order.internal_id)

                self.details(f"Remove order {str(order.internal_id)[:8]} above {bid_price:f}")

                await order_manager.controllers.mongo.store_strategy(self)

                del buy_orders[order_price]

        # TODO Put on clean trailing buy orders scripts or som'
        """
        for order_price, order in list(buy_orders.items()):
            if order_price < last_price:
                cancelled_order = await order_manager.cancel_order(order, self)

                if cancelled_order.executed_quantity:
                    converted_base_quantity += cancelled_order.executed_quantity

                self.internal_buy_order_ids.remove(order.internal_id)

                self.details(f"Remove order {str(order.internal_id)[:8]} below {last_price:f}")

                await order_manager.controllers.mongo.store_strategy(self)

                del buy_orders[order_price]
        """

        # Sell Back cancelled quantity
        if converted_base_quantity:
            print(f"{bid_price=}")
            ask_price = await self.get_last_ask_price(self.symbol, order_manager)
            await self.sell_back(converted_base_quantity, ask_price, atom, order_manager)

        # pprint(list(sorted(orders.keys())))
        # print(pair.base_asset_atom_quantity)

    async def terminate(self, order_manager: OrderManager):
        buy_orders = self.get_buy_orders(order_manager)

        pair = order_manager.get_pair(self.symbol)
        atom = pair.base_asset_atom_quantity

        converted_base_quantity = Decimal()

        for order_price, order in buy_orders.items():
            cancelled_order = await order_manager.cancel_order(order, self)

            if cancelled_order.executed_quantity:
                converted_base_quantity += cancelled_order.executed_quantity

            self.internal_buy_order_ids.remove(order.internal_id)

            self.details(f"Cancel order @ {order_price:f} => {str(order.internal_id)[:8]}")

        if converted_base_quantity:
            # print(f"{self._last_ticker_data.ask_price=}")
            ask_price = await self.get_last_ask_price(self.symbol, order_manager)
            await self.sell_back(converted_base_quantity, ask_price, atom, order_manager)

    async def sell_back(
        self,
        converted_base_quantity: Decimal,
        price: Decimal,
        atom: Decimal,
        order_manager: OrderManager,
    ):
        for atom_index in range(4):
            price = price + (atom_index * atom)

            try:
                order = await order_manager.create_order(
                    symbol=self.symbol,
                    side=Side.sell,
                    price=price,
                    quantity=converted_base_quantity,
                    market_making=True,
                    strategy=self,
                )

                break
            except OrderWouldMatch:
                self.details(f"Created sell back order aborted @ {price:f}: would match")

        self.internal_sell_order_ids.add(order.internal_id)

        await order_manager.controllers.mongo.store_strategy(self)

        self.details(f"Created sell back order @ {price:f} => {str(order.internal_id)[:8]}")

    def safe_quit_check(self, bid_price: Decimal):
        now = datetime.now()

        for price, last_timestamp in list(self._last_price_timestamps.items()):
            if last_timestamp < now - self.max_increase_retain_delta:
                del self._last_price_timestamps[price]

        if (
            len(self._last_price_timestamps) >= self.max_increase_step
            and max(self._last_price_timestamps.keys()) < bid_price
        ):
            self.details(
                f"Strategy exit @ {bid_price:f} with {len(self._last_price_timestamps)} tick increase"
            )

            raise StrategyExit()

        self._last_price_timestamps[bid_price] = now

    async def process_ticker_data(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        await self.update_buy_side(order_manager, ticker_data.bid_price)

        self.safe_quit_check(ticker_data.bid_price)

        self._last_ticker_data = ticker_data
        self._last_update = datetime.now()

    async def get_last_ask_price(self, symbol: str, order_manager: OrderManager):
        if not self._last_ticker_data:
            await order_manager.load_pairs()

            pair = order_manager.get_pair(symbol)

            return pair.ask_price
        else:
            return self._last_ticker_data.ask_price

    async def process_order(self, order: Order, order_manager: OrderManager):
        self.details("process order")

        if not order.is_filled():
            self.details("process order: not filled")
            pprint(order.dict())
            return order

        self.log_order(order, f"{order.side.capitalize()} Filled")

        if order.side == "BUY":
            await asyncio.sleep(1)

            quantity = await order_manager.get_max_base_quantity(order)
            # quantity = order.executed_quantity # * Decimal("0.999")
            # print(f"{quantity=}")

            pair = order_manager.get_pair(order.symbol)
            atom = pair.base_asset_atom_quantity

            filled_order = await order_manager.update_order(order, self)

            order_manager.clear_order(filled_order)
            self.details(
                f"Sell back order {str(filled_order.internal_id)[:8]} at {filled_order.price + atom:f}"
            )

            # quantity = order_manager.floor_base(pair, quantity)
            # print(f"floored {quantity=}")

            price = await self.get_last_ask_price(order.symbol, order_manager) + atom
            price = max(price, order.price + atom)
            try:
                sell_order = await order_manager.create_order(
                    symbol=self.symbol,
                    side=Side.sell,
                    price=price,
                    quantity=quantity,
                    market_making=True,
                    strategy=self,
                )
            except OrderWouldMatch:
                self.details(f"Created sell order aborted @ {price:f}: would match")

                await asyncio.sleep(1)

                sell_order = await order_manager.create_order(
                    symbol=self.symbol,
                    side=Side.sell,
                    price=price + atom,
                    quantity=quantity,
                    market_making=True,
                    strategy=self,
                )

            self.internal_buy_order_ids.remove(filled_order.internal_id)
            self.internal_sell_order_ids.add(sell_order.internal_id)

            await order_manager.controllers.mongo.store_strategy(self)

            self.details(f"Created sell order @ {price:f} => {str(sell_order.internal_id)[:8]}")
        elif order.side == "SELL":
            filled_order = await order_manager.update_order(order, self)

            self.internal_sell_order_ids.remove(filled_order.internal_id)
            order_manager.clear_order(filled_order)

            await order_manager.controllers.mongo.store_strategy(self)

            self.details(
                f"Order Sell Filled {str(filled_order.internal_id)[:8]} @ {filled_order.price:f}"
            )
