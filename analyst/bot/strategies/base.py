from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum, auto
from logging import getLogger
from typing import TYPE_CHECKING, Optional, Union
from uuid import UUID, uuid4

from analyst.bot.strategies.registry import RegisteredStrategy
from analyst.crypto.models import MarketStreamTicker, Order

if TYPE_CHECKING:
    from analyst.bot.order_manager import OrderManager

from flags import Flags

logger = getLogger("file")


class StrategyState(Enum):
    running = 0
    stopping = auto()
    stopped = auto()


class StrategyFlags(Flags):
    pass


class Strategy(metaclass=RegisteredStrategy):
    id: UUID
    name: str
    version: str

    created_at: datetime
    updated_at: datetime

    flags: StrategyFlags
    state: StrategyState
    lock: asyncio.Lock = asyncio.Lock()

    Flags = StrategyFlags

    def __init__(
        self,
        id: UUID,
        created_at: datetime,
        updated_at: datetime,
        flags: StrategyFlags,
        state: StrategyState,
        **kwargs
    ):
        self.id = id

        self.created_at = created_at
        self.updated_at = updated_at

        self.flags = flags
        self.state = state

    @staticmethod
    def _deserialize_timestamp(timestamp: Optional[Union[str, datetime]] = None) -> datetime:
        if not timestamp:
            return datetime.now().replace(microsecond=0)
        elif isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp)

    @classmethod
    def post_create(
        cls,
        id: Optional[Union[str, UUID]] = None,
        created_at: Optional[Union[str, datetime]] = None,
        updated_at: Optional[Union[str, datetime]] = None,
        flags: int = 0,
        state: int = 0,
        **kwargs
    ):
        if isinstance(id, str):
            id = UUID(id)

        created_at = cls._deserialize_timestamp(created_at)
        updated_at = cls._deserialize_timestamp(updated_at)

        return cls(
            id=id or uuid4(),
            created_at=created_at,
            updated_at=updated_at,
            state=StrategyState(state),
            flags=cls.Flags(flags),
            **kwargs
        )

    def dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "key": self.get_key(),
            "args": {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "flags": self.flags,
            "state": self.state,
        }

    def get_key(self):
        return ""

    def to_str(self):
        return ""

    def get_default_flags(self):
        raise NotImplementedError()

    async def setup(self, order_manager):
        raise NotImplementedError()

    async def gatekeeping(self, order_manager):
        raise NotImplementedError()

    async def process_ticker_data(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        raise NotImplementedError()

    async def process_order(self, order: Order, order_manager: OrderManager):
        raise NotImplementedError()

    async def get_stream_names(self):
        raise NotImplementedError()

    async def send_ticker_data(self, ticker_data: MarketStreamTicker, order_manager: OrderManager):
        raise NotImplementedError()

    async def send_order(self, order: Order, order_manager: OrderManager):
        raise NotImplementedError()

    @property
    def is_running(self):
        return self.state != StrategyState.stopped

    @property
    def is_stopped(self):
        return self.state == StrategyState.stopped

    @property
    def is_stopping(self):
        return self.state == StrategyState.stopping

    async def pending_stop(self, order_manager):
        if self.state == StrategyState.running:
            self.state = StrategyState.stopping

            await order_manager.controllers.mongo.store_strategy(self)

    async def stop(self, order_manager):
        if not self.is_stopped:
            self.state = StrategyState.stopped

            await order_manager.controllers.mongo.store_strategy(self)

    async def terminate(self, order_manager):
        pass
