from logging import getLogger
from typing import List

from pymongo import ASCENDING

from analyst.adapters.factory import Adapters
from analyst.bot.strategies.base import Strategy
from analyst.bot.strategies.factory import get_strategy
from analyst.repositories.utils import recover_decimal, serialize_obj

logger = getLogger("repo.strategies")


class NoStrategy(Exception):
    pass


class StrategyAlreadyExist(Exception):
    pass


class StrategyDoesNotExist(Exception):
    pass


class StrategyRepository:
    def __init__(self, adapters: Adapters, collection_name: str):
        self.mongo = adapters.mongo.get_collection(collection_name)

    async def create(self, strategy: Strategy) -> Strategy:
        logger.debug(
            f"creating id={strategy.id} name={strategy.name}:{strategy.version} key={strategy.get_key()}"
        )

        if await self.mongo.find_one({"id": strategy.id}):
            logger.error(f"already exist : id={strategy.id}")

            raise StrategyAlreadyExist(f"Strategy {strategy.id} already exists")
        else:
            await self.mongo.insert_one(serialize_obj(strategy.dict()))

            logger.info(
                f"created id={strategy.id} "
                f"name={strategy.name}:{strategy.version} "
                f"key={strategy.get_key()}"
            )

            return strategy

    async def update(self, strategy: Strategy) -> Strategy:
        logger.debug(f"updating id={strategy.id}")

        mongo_order = await self.get_by_id(id=strategy.id)

        if mongo_order.dict() != strategy.dict():
            await self.mongo.update_one({"id": mongo_order.id}, {"$set": serialize_obj(strategy.dict())})
            logger.info(f"updating successful id={strategy.id}")
        else:
            logger.info(f"nothing to update: id={strategy.id}")

        return strategy

    async def get_by_id(self, id) -> Strategy:
        if strategy_data := await self.mongo.find_one({"id": id}):
            return self._create_strategy(strategy_data)
        else:
            logger.debug(f"does not exist: id={id}")

            raise StrategyDoesNotExist(f"Strategy with id={str(id)} doesn't exists")

    @staticmethod
    def _create_strategy(strategy_data) -> Strategy:
        strategy_data.update(strategy_data["args"])

        name = strategy_data["name"]
        version = strategy_data["version"]

        strategy_cls = get_strategy(name=name, version=version)

        if strategy_cls:
            return strategy_cls.create(**recover_decimal(strategy_data))

        raise Exception(f"Strategy {name}:{version} does not exists")

    async def list(self, limit=None, **kwargs) -> List[Strategy]:
        serialized_kwargs = serialize_obj(kwargs)
        mongo_array = self.mongo.find(serialized_kwargs, sort=[("created_at", ASCENDING)])

        if limit is not None:
            count = await self.mongo.count_documents(serialized_kwargs)

            if count - limit > 0:
                mongo_array = mongo_array.skip(count - limit)

        strategies = [self._create_strategy(strategy_data) async for strategy_data in mongo_array]

        logger.debug(
            f"listing limit={limit} kwargs={serialized_kwargs}: returns {len(strategies)} strategies"
        )

        return strategies

    async def delete(self, strategy: Strategy) -> bool:
        if await self.mongo.find_one({"id": strategy.id}):
            logger.debug(f"deleting {strategy.id}")

            await self.mongo.delete_one({"id": strategy.id})

            return True
        else:
            logger.debug(f"does not exist: id={strategy.id}")

            raise StrategyDoesNotExist(f"Strategy {strategy.to_str()} doesn't exists")

    async def delete_all(self, **kwargs) -> bool:
        strategies = await self.list(**kwargs)

        for strategy in strategies:
            await self.delete(strategy)

        logger.debug(f"deleting all ({len(strategies)})")

        return True
