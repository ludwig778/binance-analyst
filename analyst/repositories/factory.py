from pydantic import BaseModel

from analyst.adapters.factory import Adapters
from analyst.repositories.order import OrderRepository
from analyst.repositories.strategy import StrategyRepository
from analyst.settings import AppSettings


class Repositories(BaseModel):
    orders: OrderRepository
    strategies: StrategyRepository

    class Config:
        arbitrary_types_allowed = True


def get_repositories(settings: AppSettings, adapters: Adapters) -> Repositories:
    return Repositories(
        orders=OrderRepository(
            adapters=adapters, collection_name="orders" if not settings.test else "test_orders"
        ),
        strategies=StrategyRepository(
            adapters=adapters, collection_name="strategies" if not settings.test else "test_strategies"
        ),
    )
