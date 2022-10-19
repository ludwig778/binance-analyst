from logging import getLogger
from typing import List
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from analyst.adapters.factory import Adapters
from analyst.crypto.models import Order
from analyst.repositories.utils import serialize_obj

logger = getLogger("repo.orders")


class NoOrder(Exception):
    pass


class OrderAlreadyExist(Exception):
    pass


class OrderDoesNotExist(Exception):
    pass


class OrderRepository:
    def __init__(self, adapters: Adapters, collection_name: str):
        self.mongo = adapters.mongo.get_collection(collection_name)

    async def create(self, order: Order) -> Order:
        logger.debug(f"creating id={order.id} symbol={order.symbol} => {order.internal_id}")

        if await self.mongo.find_one({"id": order.id, "symbol": order.symbol}):
            logger.error(f"already exist : id={order.id} symbol={order.symbol}")

            raise OrderAlreadyExist(f"Order {order.id} => {order.symbol} already exists")
        elif await self.mongo.find_one({"internal_id": order.internal_id}):
            logger.error(f"already exist : id={order.id} symbol={order.symbol}")

            raise OrderAlreadyExist(f"Order internal_id={order.internal_id} already exists")
        else:
            await self.mongo.insert_one(serialize_obj(order.dict()))

            logger.info(f"created id={order.id} symbol={order.symbol} => {order.internal_id}")

            return order

    async def update(self, order: Order) -> Order:
        logger.debug(f"updating internal_id={order.internal_id}")

        mongo_order = await self.get_by_id(internal_id=order.internal_id)

        if mongo_order.dict() != order.dict():
            await self.mongo.update_one(
                {"internal_id": order.internal_id}, {"$set": serialize_obj(order.dict())}
            )

            logger.info(f"update successful: internal_id={order.internal_id}")
        else:
            logger.info(f"nothing to update: internal_id={order.internal_id}")

        return order

    async def get(self, order_id: int, symbol: str) -> Order:
        if order_data := await self.mongo.find_one({"id": order_id, "symbol": symbol}):
            return Order(**order_data)
        else:
            logger.debug(f"does not exist: id={order_id} symbol={symbol}")

            raise OrderDoesNotExist(f"Order {order_id} => {symbol} doesn't exists")

    async def get_by_id(self, internal_id: UUID) -> Order:
        if order_data := await self.mongo.find_one({"internal_id": internal_id}):
            return Order(**order_data)
        else:
            logger.debug(f"does not exist: internal_id={internal_id}")

            raise OrderDoesNotExist(f"Order internal_id={internal_id} doesn't exists")

    async def list(self, limit=None, **kwargs) -> List[Order]:
        serialized_kwargs = serialize_obj(kwargs)
        mongo_array = self.mongo.find(serialized_kwargs, sort=[("created_at", ASCENDING)])

        if limit is not None:
            count = await self.mongo.count_documents(serialized_kwargs)

            if count - limit > 0:
                mongo_array = mongo_array.skip(count - limit)

        orders = [Order(**order_data) async for order_data in mongo_array]

        logger.debug(f"listing limit={limit} kwargs={serialized_kwargs}: returns {len(orders)} orders")

        return orders

    async def get_latest(self, symbol: str) -> Order:
        order_data = await self.mongo.find_one({"symbol": symbol}, sort=[("created_at", DESCENDING)])

        if not order_data:
            logger.debug(f"get latest {symbol=}: no orders")
            # return None
            raise NoOrder(f"No orders for {symbol}")

        order = Order(**order_data)

        logger.debug(f"get latest {symbol=}: got {order.internal_id}")

        return order

    async def delete(self, order: Order) -> bool:
        if await self.mongo.find_one({"internal_id": order.internal_id}):
            logger.debug(f"deleting {order.internal_id}")

            await self.mongo.delete_one({"internal_id": order.internal_id})

            return True
        else:
            logger.debug(f"does not exist: internal_id={order.internal_id}")

            raise OrderDoesNotExist(f"Order internal_id={order.internal_id} doesn't exists")

    async def delete_all(self, **kwargs) -> bool:
        orders = await self.list(**kwargs)

        for order in orders:
            await self.delete(order)

        logger.debug(f"deleting all ({len(orders)})")

        return True
