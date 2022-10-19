import json
from logging import getLogger
from typing import List, Optional

from analyst.adapters.factory import Adapters
from analyst.bot.strategies.base import Strategy, StrategyState
from analyst.crypto.models import Order
from analyst.repositories.factory import Repositories
from analyst.repositories.order import OrderDoesNotExist
from analyst.repositories.strategy import StrategyAlreadyExist, StrategyDoesNotExist
from analyst.repositories.utils import serialize_obj

logger = getLogger("controllers.mongo")


class MongoController:
    def __init__(self, adapters: Adapters, repositories: Repositories):
        self.adapters = adapters
        self.repositories = repositories

    async def store_strategy(self, strategy: Strategy) -> Strategy:
        logger.info(f"store strategy {strategy.id}")

        try:
            strategy = await self.repositories.strategies.create(strategy)

            logger.info(f"store strategy {strategy.id}: create")
        except StrategyAlreadyExist:
            strategy = await self.repositories.strategies.update(strategy)

            logger.info(f"store strategy {strategy.id}: update")

        return strategy

    async def update_strategy(self, strategy: Strategy) -> Strategy:
        logger.info(f"update strategy {strategy.id}")

        return await self.repositories.strategies.update(strategy)

    async def delete_strategy(self, strategy: Strategy) -> bool:
        try:
            deleted = await self.repositories.strategies.delete(strategy)

            logger.info(f"remove strategy {strategy.id} ok")

            return deleted
        except StrategyDoesNotExist:
            logger.info(f"remove strategy {strategy.id} does not exist")

            return False

    async def get_strategies(self, **kwargs) -> List[Strategy]:
        strategies = await self.repositories.strategies.list(**kwargs)

        logger.info(f"get strategies: {json.dumps(serialize_obj(kwargs))} => returns {len(strategies)}")

        return strategies

    async def get_strategy(self, strategy_id) -> Optional[Strategy]:
        try:
            logger.info(f"get strategy {strategy_id}")

            return await self.repositories.strategies.get_by_id(strategy_id)
        except StrategyDoesNotExist:
            logger.info(f"get strategy {strategy_id}: does not exists")

            return None

    async def get_running_strategies(self) -> List[Strategy]:
        strategies = await self.repositories.strategies.list(state={"$nin": [StrategyState.stopped]})

        logger.info(f"get running strategies => {len(strategies)}")

        return strategies

    async def get_strategy_last_order(self, strategy: Strategy) -> Optional[Order]:
        orders = await self.repositories.orders.list(strategy_id=strategy.id, limit=1)

        last_order = orders[0] if orders else None

        logger.info(
            f"get last strategy {strategy.id} order => {last_order.internal_id if last_order else None}"
        )

        return last_order

    async def get_strategy_orders(self, strategy: Strategy, limit: Optional[int] = None) -> List[Order]:
        orders = await self.repositories.orders.list(strategy_id=strategy.id, limit=limit)

        logger.info(f"get strategy {strategy.id} orders => {len(orders)}")

        return orders

    async def store_order(self, order: Order, strategy: Optional[Strategy] = None) -> Order:
        logger.debug(f"store order {order.internal_id}")

        if strategy:
            order.strategy_id = strategy.id

        try:
            existing_order = await self.repositories.orders.get(order.id, order.symbol)

            order.internal_id = existing_order.internal_id

            if not order.strategy_id:
                order.internal_id = existing_order.internal_id

            order = await self.repositories.orders.update(order)

            logger.info(f"store order {order.internal_id}: update")
        except OrderDoesNotExist:
            order = await self.repositories.orders.create(order)

            logger.info(f"store order {order.internal_id}: create")

        return order

    async def update_order(self, order: Order, strategy: Optional[Strategy] = None) -> Order:
        if strategy:
            order.strategy_id = strategy.id

        order = await self.repositories.orders.update(order)

        logger.info(f"update order {order.internal_id}")

        return order

    async def get_orders(self, **kwargs) -> List[Order]:
        orders = await self.repositories.orders.list(**kwargs)

        logger.info(
            f"get orders: {json.dumps(serialize_obj(kwargs, serialize_uuid=True))} "
            f"=> returns {len(orders)}"
        )

        return orders

    async def get_order(self, order_id, symbol) -> Optional[Order]:
        try:
            order = await self.repositories.orders.get(order_id, symbol)

            logger.info(f"get order: {order_id=} {symbol=} ok")

            return order
        except OrderDoesNotExist:
            logger.info(f"get order: {order_id=} {symbol=} does not exist")

            return None

    async def get_order_by_id(self, internal_id) -> Optional[Order]:
        try:
            order = await self.repositories.orders.get_by_id(internal_id)

            logger.info(f"get order: {internal_id=} ok")

            return order
        except OrderDoesNotExist:
            logger.info(f"get order: {internal_id=} does not exist")

            return None

    async def delete_order(self, order: Order) -> bool:
        try:
            deleted = await self.repositories.orders.delete(order)

            logger.info(f"delete order: {order.internal_id} ok")

            return deleted
        except OrderDoesNotExist:
            logger.info(f"delete order: {order.internal_id} does not exist")

            return False
