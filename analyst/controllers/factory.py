from analyst.adapters.factory import Adapters
from analyst.controllers.binance import BinanceController

from pydantic import BaseModel


class Controllers(BaseModel):
    binance: BinanceController

    class Config:
        arbitrary_types_allowed = True


def get_controllers(adapters: Adapters) -> Controllers:
    return Controllers(
        binance=BinanceController(adapters=adapters),
    )
