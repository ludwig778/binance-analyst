from typing import Union

from pydantic import BaseModel

from binance_analyst.adapters import Adapters
from binance_analyst.controllers.account import AccountController
from binance_analyst.controllers.exchange import ExchangeController
from binance_analyst.controllers.pair import PairController

ControllerInstance = Union[AccountController, ExchangeController, PairController]


class Controllers(BaseModel):
    account: AccountController
    exchange: ExchangeController
    pair: PairController

    class Config:
        arbitrary_types_allowed = True


def get_controllers(adapters: Adapters) -> Controllers:
    return Controllers(
        account=AccountController(adapters),
        exchange=ExchangeController(adapters),
        pair=PairController(adapters),
    )
