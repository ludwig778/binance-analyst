from copy import deepcopy
from datetime import datetime
from logging import getLogger
from typing import Optional

from analyst.bot.order_manager import OrderManager
from analyst.bot.strategies.base import Strategy
from analyst.crypto.models import Order

logger = getLogger("mocked_order_manager")


class MockedOrderManager(OrderManager):
    orders_out = 1

    async def fill_order(self, order: Order, strategy: Optional[Strategy] = None):
        order = deepcopy(order)
        order.status = "FILLED"
        order.executed_quantity = order.requested_quantity

        order = await self.controllers.mongo.store_order(order, strategy)

        self.orders[order.internal_id] = order

        return order

    async def cancel_order(self, order, strategy: Optional[Strategy] = None):
        order.status = "CANCELLED"

        self.log_order(order, "Cancelled")

        order = await self.update_order(order, strategy)

        self.orders.pop(order.internal_id, None)

        return order

    async def _create_order(self, **kwargs):
        if "id" not in kwargs:
            kwargs.setdefault("id", self.orders_out)
            self.orders_out += 1

        if kwargs["type"] == "MARKET":
            kwargs["status"] = "FILLED"
            kwargs["executed_quantity"] = kwargs["quantity"]
        else:
            kwargs.setdefault("status", "NEW")

        kwargs.setdefault("requested_quantity", kwargs["quantity"])
        kwargs.setdefault("price", "0.0")
        kwargs.setdefault("created_at", datetime.now())
        kwargs.setdefault("updated_at", datetime.now())

        return Order.create(**kwargs)
