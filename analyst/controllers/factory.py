from pydantic import BaseModel

from analyst.adapters.factory import Adapters
from analyst.controllers.binance import BinanceController
from analyst.controllers.mongo import MongoController
from analyst.repositories.factory import Repositories


class Controllers(BaseModel):
    binance: BinanceController
    mongo: MongoController

    class Config:
        arbitrary_types_allowed = True


def get_controllers(adapters: Adapters, repositories: Repositories) -> Controllers:
    return Controllers(
        binance=BinanceController(adapters=adapters),
        mongo=MongoController(adapters=adapters, repositories=repositories),
    )
