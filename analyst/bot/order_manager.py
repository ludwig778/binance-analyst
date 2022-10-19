from __future__ import annotations

import json
import logging
import operator
from decimal import Decimal
from enum import Enum, auto
from logging import getLogger
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from analyst.bot.strategies.base import Strategy
from analyst.controllers.factory import Controllers
from analyst.crypto.exceptions import PriceMustBeSetOnMarketMakingOrder
from analyst.crypto.models import CoinAmount, Order, OutboundAccountPosition, Pair
from analyst.repositories.utils import serialize_account_obj
from analyst.utils import trunk_uuid

logger = getLogger("order_manager")


class Side(Enum):
    buy = "BUY"
    sell = "SELL"

    def reverse(self, state: bool = False):
        if state:
            return self.buy if self.name == "SELL" else self.sell

        return self


class PairSide(Enum):
    base = auto()
    quote = auto()


class OrderManager:
    def __init__(self, controllers: Controllers):
        self.controllers = controllers
        self.orders: Dict[UUID, Order] = {}

    async def setup(self):
        logger.debug("setup")

        await self.load_account()
        await self.load_pairs()

    async def load_account(self):
        logger.debug("load account")

        self.account = await self.controllers.binance.load_account()

    async def load_pairs(self):
        logger.debug("load pairs")

        self.pairs = await self.controllers.binance.load_pairs()

    # def get_pair(self, symbol) -> Optional[Pair]:
    def get_pair(self, symbol) -> Pair:
        return self.pairs[symbol]

    async def get_fee_optimized_quantity_available(self, order: Order) -> Decimal:
        await self.load_account()

        pair = self.get_pair(order.symbol)

        order_quantity = order.executed_quantity
        min_order_quantity = order_quantity * Decimal("0.999")
        account_quantity = self.get_account_quantity(pair, PairSide.base)

        if order_quantity <= account_quantity:
            return order_quantity

        return min_order_quantity + (account_quantity % min_order_quantity) // pair.step_size

    def get_order(self, order_internal_id: UUID) -> Optional[Order]:
        return self.orders.get(order_internal_id)

    def clear_order(self, order: Order) -> None:
        logger.info(f"clear order {order.internal_id}")

        self.orders.pop(order.internal_id, None)

    async def update_order(self, order: Order, strategy: Optional[Strategy] = None):
        logger.info(f"update order {order.internal_id} strategy_id={strategy.id if strategy else None}")

        order = await self.controllers.mongo.store_order(order, strategy)

        self.orders[order.internal_id] = order

        return order

    async def cancel_order(self, order, strategy: Optional[Strategy] = None):
        logger.info(f"cancel order {order.internal_id} strategy_id={strategy.id if strategy else None}")

        order = await self.controllers.binance.cancel_order(order)

        self.log_order(order, "Cancelled")

        order = await self.update_order(order, strategy)

        self.orders.pop(order.internal_id, None)

        return order

    def update_account_with_live_data(self, new_account_position: OutboundAccountPosition):
        logger.info("update account with live data")

        for balance in new_account_position.balances:
            logger.info(f"update account coin {balance.coin} = {balance.free}")

            self.account[balance.coin] = CoinAmount(coin=balance.coin, quantity=balance.free)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"new account balances: {json.dumps(serialize_account_obj(self.account), indent=2)}"
            )

    def get_account_quantity(self, pair: Pair, pair_side: PairSide):
        if pair_side is PairSide.base:
            coin_name = pair.base
        else:
            coin_name = pair.quote

        coin = self.account.get(coin_name)

        quantity = Decimal(str(coin.quantity if coin else 0))

        logger.info(f"get account quantity {coin} => {quantity}")

        return quantity

    def has_sufficient_quantity(self, pair: Pair, quantity: Decimal, pair_side: PairSide) -> bool:
        account_quantity = self.get_account_quantity(pair, pair_side)

        is_sufficient = quantity <= account_quantity

        logger.info(f"has sufficient quantity: {is_sufficient} => {pair.symbol} on {pair_side.name}")

        return is_sufficient

    def truncate_base_quantity(self, pair, quantity, ceil: bool = False):
        quotient, remainder = divmod(quantity, pair.step_size)

        floored_quantity = quotient * pair.step_size

        if remainder and ceil:
            floored_quantity += pair.step_size

        logger.debug(f"floored quantity: {quantity} on {pair.symbol} => {floored_quantity}")

        return floored_quantity

    def convert_quantity(self, quantity: Decimal, price: Decimal, to: PairSide) -> Decimal:
        if to is PairSide.base:
            op = operator.truediv
        else:
            op = operator.mul

        converted_quantity = op(Decimal(quantity), price)

        logger.debug(
            f"convert: {quantity} {'/' if op == operator.truediv else '*'} {price}"
            f" => {converted_quantity}"
        )

        return converted_quantity

    def log_order(self, order: Order, text, label=""):
        pass
        # LogFormat.log_order(
        #    logger, order, text, label or "ORDER"
        # )

    async def _create_order(self, **kwargs):
        return await self.controllers.binance.create_order(**kwargs)

    async def create_order(
        self,
        symbol: str,
        side: Side,
        quantity: Decimal,
        price: Decimal = Decimal(),
        market_making: bool = False,
        reverse: bool = False,
        strategy: Optional[Strategy] = None,
    ):
        order_creation_id = trunk_uuid(uuid4(), length=4)

        pair = self.get_pair(symbol)

        if reverse:
            side = side.reverse(True)

        quantity = self.truncate_base_quantity(pair, quantity, ceil=True)

        if market_making:
            if not price:
                raise PriceMustBeSetOnMarketMakingOrder()

            logger.debug(
                f"create order: #{order_creation_id} {side.value} {symbol}: {quantity} @ {price} #maker"
            )

            order = await self._create_order(
                symbol=symbol,
                side=side.value,
                type="LIMIT_MAKER",
                price=f"{price:f}",
                quantity=quantity,
            )

            self.log_order(order, f"{side.name.capitalize()} Maker {quantity} @ {price:f}")
        else:
            logger.debug(f"create order: #{order_creation_id} {side.value} {symbol}: {quantity} #taker")

            order = await self._create_order(
                symbol=symbol, side=side.value, type="MARKET", quantity=quantity
            )

            self.log_order(order, f"{side.name.capitalize()} Market {quantity}")

        logger.info(
            f"created order: #{order_creation_id} "
            f"order_id={order.internal_id} "
            f"strategy_id={strategy.id if strategy else None}"
        )

        return await self.update_order(order, strategy)

    async def sell_all_maker(self, symbol: str, price: Decimal, strategy: Optional[Strategy] = None):
        order_creation_id = trunk_uuid(uuid4(), length=4)

        pair = self.get_pair(symbol)

        quantity = float(
            self.truncate_base_quantity(pair, self.get_account_quantity(pair, PairSide.base))
        )

        logger.debug(f"create order: #{order_creation_id} SELL all {symbol}: {quantity} @ {price} #maker")

        order = await self._create_order(
            symbol=symbol, side="SELL", type="LIMIT_MAKER", price=f"{price:f}", quantity=quantity
        )

        logger.info(
            f"created order: #{order_creation_id} "
            f"order_id={order.internal_id} "
            f"strategy_id={strategy.id if strategy else None}"
        )

        return await self.update_order(order, strategy)

    async def sell_all_market(self, symbol: str, strategy: Optional[Strategy] = None):
        order_creation_id = trunk_uuid(uuid4(), length=4)

        pair = self.get_pair(symbol)

        quantity = float(
            self.truncate_base_quantity(pair, self.get_account_quantity(pair, PairSide.base))
        )

        logger.debug(f"create order: #{order_creation_id} SELL all {symbol}: {quantity} #taker")

        order = await self._create_order(symbol=symbol, side="SELL", type="MARKET", quantity=quantity)

        logger.info(
            f"created order: #{order_creation_id} "
            f"order_id={order.internal_id} "
            f"strategy_id={strategy.id if strategy else None}"
        )

        return await self.update_order(order, strategy)

    async def setup_order(self, internal_order_id: UUID) -> Optional[Order]:
        logger.debug(f"setup order: {internal_order_id}")

        order = await self.controllers.mongo.get_order_by_id(internal_order_id)

        if order and order.is_open():
            logger.info(f"setup order: fetch and update {internal_order_id}")

            return await self.fetch_and_update_order(order)
        else:
            logger.debug(f"setup order: skip {'closed' if order else 'not existing'} {internal_order_id}")

            return None

    async def fetch_and_update_order(self, order: Order) -> Order:
        logger.debug(f"fetch and update order: internal_id={order.internal_id}")

        updated_order = await self.controllers.binance.get_updated_order(order)

        updated_order.strategy_id = order.strategy_id

        order = await self.controllers.mongo.store_order(updated_order)

        self.orders[order.internal_id] = order

        return order

    async def get_updated_orders(self) -> List[Order]:
        logger.debug("get updated orders")

        updated_orders = []

        for order in list(self.orders.values()):
            updated_order = await self.fetch_and_update_order(order)

            if order != updated_order:
                updated_orders.append(updated_order)

        logger.info(f"get updated orders: {len(updated_orders)} changes")

        return updated_orders
