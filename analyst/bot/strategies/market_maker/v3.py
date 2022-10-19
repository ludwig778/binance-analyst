from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Union
from uuid import UUID

from analyst.bot.exceptions import StrategyHalt
from analyst.bot.order_manager import PairSide, Side
from analyst.bot.strategies.base import Strategy, StrategyFlags
from analyst.crypto.exceptions import OrderWouldMatch
from analyst.crypto.models import MarketStreamTicker, Order
from analyst.repositories.utils import from_isoformat_to_timedelta, serialize_order_obj
from analyst.utils import trunk_uuid

if TYPE_CHECKING:
    from analyst.bot.order_manager import OrderManager

logger = getLogger("market_maker.v3")


class MarketMakerV3(Strategy):
    name = "market_maker"
    version = "v3"

    class Flags(StrategyFlags):
        insufficient_fund = ()

    def __init__(
        self,
        symbol: str,
        quote_quantity: Decimal,
        interval: Decimal,
        reverse: bool,
        internal_buy_order_ids: Set[UUID],
        internal_sell_order_ids: Set[UUID],
        cleanup_interval: timedelta,
        max_buy_orders: int,
        max_increase_step: int,
        max_increase_retain_delta: timedelta,
        **kwargs,
    ):
        super(MarketMakerV3, self).__init__(**kwargs)

        self.symbol = symbol
        self.quote_quantity = quote_quantity
        self.interval = interval
        self.reverse = reverse

        self.internal_buy_order_ids = internal_buy_order_ids
        self.internal_sell_order_ids = internal_sell_order_ids

        self.cleanup_interval = cleanup_interval
        self.max_buy_orders = max_buy_orders
        self.max_increase_step = max_increase_step
        self.max_increase_retain_delta = max_increase_retain_delta

        self._last_ticker_data: Optional[MarketStreamTicker] = None
        self._last_cleanup: Optional[datetime] = None
        self._last_update: Optional[datetime] = None

        self._last_price_timestamps: Dict[Decimal, datetime] = {}

    async def setup(self, order_manager):
        logger.info(f"setup strategy_id={trunk_uuid(self.id)}")

        changed = False

        # TODO DO THIS IN ORDER MANAGER
        for internal_order_id in list(self.internal_buy_order_ids):
            order = await order_manager.setup_order(internal_order_id)

            if not order or order.status == "FILLED":
                changed = True

                self.internal_buy_order_ids.remove(internal_order_id)

        for internal_order_id in list(self.internal_sell_order_ids):
            order = await order_manager.setup_order(internal_order_id)

            if not order or order.status == "FILLED":
                changed = True

                self.internal_sell_order_ids.remove(internal_order_id)

        if changed:
            await order_manager.controllers.mongo.store_strategy(self)

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "key": self.get_key(),
            "args": {
                "symbol": self.symbol,
                "quote_quantity": self.quote_quantity,
                "interval": self.interval,
                "reverse": self.reverse,
                "internal_buy_order_ids": self.internal_buy_order_ids,
                "internal_sell_order_ids": self.internal_sell_order_ids,
                "cleanup_interval": self.cleanup_interval,
                "max_buy_orders": self.max_buy_orders,
                "max_increase_step": self.max_increase_step,
                "max_increase_retain_delta": self.max_increase_retain_delta,
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
        interval,
        reverse: bool = False,
        internal_buy_order_ids: Union[Optional[List[UUID]], Set[UUID]] = None,
        internal_sell_order_ids: Union[Optional[List[UUID]], Set[UUID]] = None,
        cleanup_interval: timedelta = timedelta(minutes=30),
        max_buy_orders: int = 2,
        max_increase_step: int = 0,
        max_increase_retain_delta: timedelta = timedelta(days=1),
        **kwargs,
    ):
        if not isinstance(quote_quantity, Decimal):
            quote_quantity = Decimal(quote_quantity)

        if not isinstance(interval, Decimal):
            interval = Decimal(interval)

        internal_buy_order_ids = set(internal_buy_order_ids) if internal_buy_order_ids else set([])
        internal_sell_order_ids = set(internal_sell_order_ids) if internal_sell_order_ids else set([])

        if isinstance(cleanup_interval, str):
            cleanup_interval = from_isoformat_to_timedelta(cleanup_interval)

        if isinstance(max_increase_retain_delta, str):
            max_increase_retain_delta = from_isoformat_to_timedelta(max_increase_retain_delta)

        return cls.post_create(
            quote_quantity=quote_quantity,
            interval=interval,
            reverse=reverse,
            internal_buy_order_ids=internal_buy_order_ids,
            internal_sell_order_ids=internal_sell_order_ids,
            cleanup_interval=cleanup_interval,
            max_buy_orders=max_buy_orders,
            max_increase_step=max_increase_step,
            max_increase_retain_delta=max_increase_retain_delta,
            **kwargs,
        )

    @staticmethod
    def get_args_meta():
        return {"symbol": str, "quote_quantity": float, "interval": float, "reverse": bool}

    @staticmethod
    def get_update_args_meta():
        return {"max_buy_orders": int}

    def get_default_flags(self):
        return self.Flags.no_flags

    def get_key(self):
        return f"{self.symbol}:{self.quote_quantity}:{self.interval}:{self.reverse}"

    def to_str(self):
        return f"{self.name}:{self.version} on {self.symbol}"

    def get_stream_names(self) -> List[str]:
        return [f"{self.symbol.lower()}@ticker"]

    def gatekeeping(self, order_manager: OrderManager):
        try:
            pair = order_manager.get_pair(self.symbol)
        except KeyError:
            raise Exception(f"Pair {self.symbol} does not exist strategy_id={trunk_uuid(self.id)}")

        if self.interval <= 0:
            raise Exception(f"Interval must be positive strategy_id={trunk_uuid(self.id)}")

        if not order_manager.has_sufficient_quantity(pair, self.quote_quantity, PairSide.quote):
            raise Exception(f"Insufficient funds strategy_id={trunk_uuid(self.id)}")

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
        logger.debug(f"update buy side strategy_id={trunk_uuid(self.id)}")

        buy_orders = self.get_buy_orders(order_manager)
        sell_orders = self.get_sell_orders(order_manager)

        pair = order_manager.get_pair(self.symbol)
        atom = self.interval

        floored_bid_price = (bid_price // self.interval) * self.interval

        converted_base_quantity = Decimal()

        set_buy_orders = 0
        for atom_index in range(25):
            price = floored_bid_price - (atom_index * atom)

            if price <= 0:
                break

            order = buy_orders.get(price)

            if atom_index == 0 and len(sell_orders.get(price + atom, ())):
                continue

            base_quantity = order_manager.truncate_base_quantity(
                pair,
                order_manager.convert_quantity(self.quote_quantity, price, to=PairSide.base),
                ceil=True,
            )

            if order and order.requested_quantity != base_quantity:
                cancelled_order = await order_manager.cancel_order(order, self)

                if cancelled_order.executed_quantity:
                    converted_base_quantity += cancelled_order.executed_quantity

                del buy_orders[cancelled_order.price]
                self.internal_buy_order_ids.remove(order.internal_id)

                logger.info(
                    f"cancel order @ {price:f} "
                    f"strategy_id={trunk_uuid(self.id)} => {order.internal_id}"
                )

                order = None

            if not order:
                if not order_manager.has_sufficient_quantity(pair, self.quote_quantity, PairSide.quote):
                    logger.warning(
                        f"cancel order @ {price:f} "
                        f"strategy_id={trunk_uuid(self.id)}: insufficient fund"
                    )

                    raise StrategyHalt()

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
                    logger.info(
                        f"created order aborted @ {price:f} "
                        f"strategy_id={trunk_uuid(self.id)}: would match"
                    )

                    if atom_index == 24:
                        logger.warning(
                            f"could not create order @ {price:f} "
                            f"strategy_id={trunk_uuid(self.id)}: halting"
                        )

                        raise StrategyHalt()

                    continue

                buy_orders[order.price] = order

                self.internal_buy_order_ids.add(order.internal_id)

                await order_manager.controllers.mongo.store_strategy(self)

                logger.info(
                    f"created order @ {price:f} "
                    f"strategy_id={trunk_uuid(self.id)} => {order.internal_id}"
                )

            set_buy_orders += 1

            if set_buy_orders >= self.max_buy_orders:
                logger.debug(f"update buy side: {set_buy_orders} set")

                break

        # Cancel buy order above BID PRICE (already filled?)
        for order_price, order in list(buy_orders.items()):
            if order_price > floored_bid_price:
                cancelled_order = await order_manager.cancel_order(order, self)

                if cancelled_order.executed_quantity:
                    converted_base_quantity += cancelled_order.executed_quantity

                self.internal_buy_order_ids.remove(order.internal_id)

                logger.info(
                    f"cancel order {order.internal_id} "
                    f"strategy_id={trunk_uuid(self.id)}: "
                    f"above {floored_bid_price:f}"
                )

                await order_manager.controllers.mongo.store_strategy(self)

                del buy_orders[order_price]

        if converted_base_quantity:
            await self.sell_back(converted_base_quantity, floored_bid_price + atom, atom, order_manager)

    async def cleanup_buy_side(self, order_manager: OrderManager, bid_price: Decimal):
        logger.debug(f"cleanup buy side strategy_id={trunk_uuid(self.id)}")

        buy_orders = self.get_buy_orders(order_manager)

        floored_bid_price = (bid_price // self.interval) * self.interval
        atom = self.interval

        converted_base_quantity = Decimal()

        if len(buy_orders) <= self.max_buy_orders:
            return

        sorted_buy_orders = list(sorted(buy_orders.items(), key=lambda x: x[0], reverse=True))

        for price, order in sorted_buy_orders[self.max_buy_orders:]:
            cancelled_order = await order_manager.cancel_order(order, self)

            if cancelled_order.executed_quantity:
                converted_base_quantity += cancelled_order.executed_quantity

            self.internal_buy_order_ids.remove(order.internal_id)

            logger.info(
                f"cleanup cancel order @ {price:f} "
                f"strategy_id={trunk_uuid(self.id)} => {order.internal_id}"
            )

            await order_manager.controllers.mongo.store_strategy(self)

            del buy_orders[price]

        if converted_base_quantity:
            await self.sell_back(converted_base_quantity, floored_bid_price + atom, atom, order_manager)

    async def terminate(self, order_manager: OrderManager) -> Optional[Order]:
        logger.info(f"terminate strategy_id={trunk_uuid(self.id)}")

        buy_orders = self.get_buy_orders(order_manager)

        converted_base_quantity = Decimal()

        for order in buy_orders.values():
            cancelled_order = await order_manager.cancel_order(order, self)

            if cancelled_order.executed_quantity:
                converted_base_quantity += cancelled_order.executed_quantity

            self.internal_buy_order_ids.remove(order.internal_id)

            logger.info(f"cancel order {order.internal_id} " f"strategy_id={trunk_uuid(self.id)}")

        if converted_base_quantity:
            sell_order = await order_manager.create_order(
                symbol=self.symbol, side=Side.sell, quantity=converted_base_quantity, strategy=self
            )

            logger.info(
                "created sell back market order "
                f"strategy_id={trunk_uuid(self.id)} => {sell_order.internal_id}"
            )

            return sell_order
        else:
            return None

    async def sell_back(
        self,
        converted_base_quantity: Decimal,
        base_price: Decimal,
        atom: Decimal,
        order_manager: OrderManager,
    ) -> Order:
        logger.info(f"sell back {converted_base_quantity} " f"strategy_id={trunk_uuid(self.id)}")

        for atom_index in range(20):
            price = base_price + (atom_index * atom)

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
                logger.info(
                    f"created sell back order aborted @ {price:f} "
                    f"strategy_id={trunk_uuid(self.id)}: would match"
                )

                if atom_index == 19:
                    logger.warning(
                        "could not create sell back order " f"strategy_id={trunk_uuid(self.id)}: halting"
                    )

                    raise StrategyHalt()

        self.internal_sell_order_ids.add(order.internal_id)

        await order_manager.controllers.mongo.store_strategy(self)

        logger.info(
            f"created sell back order @ {price:f} "
            f"strategy_id={trunk_uuid(self.id)} => {order.internal_id}"
        )

        return order

    def safe_stop_check(self, bid_price: Decimal):
        if not self.max_increase_step:
            return

        now = datetime.now()

        floored_bid_price = (bid_price // self.interval) * self.interval

        for price, last_timestamp in list(self._last_price_timestamps.items()):
            if last_timestamp < now - self.max_increase_retain_delta:
                del self._last_price_timestamps[price]

        if (
            len(self._last_price_timestamps) >= self.max_increase_step
            and max(self._last_price_timestamps.keys()) < bid_price
        ):
            logger.info(
                f"strategy safe stop @ {bid_price:f} "
                f"strategy_id={trunk_uuid(self.id)} "
                f"with {len(self._last_price_timestamps)} tick increase"
            )

            raise StrategyHalt()

        self._last_price_timestamps[floored_bid_price] = now

    async def process_ticker_data(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        now = datetime.now()

        await self.update_buy_side(order_manager, ticker_data.bid_price)

        self.safe_stop_check(ticker_data.bid_price)

        if not self._last_cleanup or self._last_cleanup + self.cleanup_interval <= now:
            await self.cleanup_buy_side(order_manager, ticker_data.bid_price)

            self._last_cleanup = now

        self._last_ticker_data = ticker_data
        self._last_update = now

    async def process_order(self, order: Order, order_manager: OrderManager):
        serialized_order = json.dumps(serialize_order_obj(order.dict()))

        if not order.is_filled():
            logger.info(
                f"process order strategy_id={trunk_uuid(self.id)}: " f"not filled {serialized_order}"
            )

            return order

        logger.info(f"process order strategy_id={trunk_uuid(self.id)}: " f"not filled {serialized_order}")

        if order.side == "BUY":
            await asyncio.sleep(1)

            quantity = await order_manager.get_fee_optimized_quantity_available(order)
            filled_order = await order_manager.update_order(order, self)

            atom = self.interval

            logger.info(
                f"buy order filled {filled_order.internal_id} "
                f"strategy_id={trunk_uuid(self.id)}: "
                f"{filled_order.executed_quantity:f} @ {filled_order.price:f}"
            )

            order_manager.clear_order(filled_order)

            sell_order = await self.sell_back(quantity, order.price + atom, self.interval, order_manager)

            self.internal_buy_order_ids.remove(filled_order.internal_id)
            self.internal_sell_order_ids.add(sell_order.internal_id)

            await order_manager.controllers.mongo.store_strategy(self)
        elif order.side == "SELL":
            filled_order = await order_manager.update_order(order, self)

            self.internal_sell_order_ids.remove(filled_order.internal_id)
            order_manager.clear_order(filled_order)

            await order_manager.controllers.mongo.store_strategy(self)

            logger.info(
                f"sell order filled {filled_order.internal_id} "
                f"strategy_id={trunk_uuid(self.id)}: "
                f"{filled_order.executed_quantity:f} @ {filled_order.price:f}"
            )
