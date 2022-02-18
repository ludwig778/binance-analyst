from typing import Union

from pydantic import BaseModel

from binance_analyst.adapters import get_adapters
from binance_analyst.repositories.account import AccountRepository
from binance_analyst.repositories.exchange import ExchangeRepository
from binance_analyst.repositories.pair import PairRepository

RepositoryInstance = Union[AccountRepository, ExchangeRepository, PairRepository]


class Repositories(BaseModel):
    account: AccountRepository
    exchange: ExchangeRepository
    pair: PairRepository

    class Config:
        arbitrary_types_allowed = True


def get_repositories() -> Repositories:
    adapters = get_adapters()

    return Repositories(
        account=AccountRepository(adapters),
        exchange=ExchangeRepository(adapters),
        pair=PairRepository(adapters),
    )
