from typing import Union

from pydantic import BaseModel

from binance_analyst.adapters import get_adapters
from binance_analyst.repositories.account import AccountRepository
from binance_analyst.repositories.pair import PairRepository

RepositoryInstance = Union[PairRepository, AccountRepository]


class Repositories(BaseModel):
    pair: PairRepository
    account: AccountRepository

    class Config:
        arbitrary_types_allowed = True


def get_repositories() -> Repositories:
    adapters = get_adapters()

    return Repositories(pair=PairRepository(adapters), account=AccountRepository(adapters))
