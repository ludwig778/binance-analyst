import asyncio
import hashlib
import hmac
import json
import logging
from copy import deepcopy
from datetime import datetime, timedelta
from logging import getLogger
from time import sleep
from typing import Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
import websockets
from pandas import DataFrame, DatetimeIndex
from pydantic import BaseModel, Field

from analyst.adapters.types import ParamsDict
from analyst.crypto.exceptions import BinanceError, InvalidInterval, WrongDatetimeRange

logger = getLogger("adapters.binance")


class BinanceWebSocketConnectionClosed(Exception):
    pass


class BinanceWeights(BaseModel):
    amount: int = Field(alias="x-mbx-used-weight", default=0)
    amount_1m: int = Field(alias="x-mbx-used-weight-1m", default=0)

    def set(self, value: int):
        self.amount = value
        self.amount_1m = value

    def reset(self):
        self.set(0)

    def __add__(self, value: int):
        self = deepcopy(self)
        self += value

        return self

    def __iadd__(self, value: int):
        self.amount += value
        self.amount_1m += value

        return self


class BinanceMetadata(BaseModel):
    weights: BinanceWeights
    server_time: datetime


class BinanceAdapter:
    api_weight_threshold = 1150
    api_possible_intervals = [
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1d",
        "3d",
        "1w",
        "1M",
    ]

    def __init__(self, settings):
        self.settings = settings

    async def get_session(self):
        session = aiohttp.ClientSession()
        session.headers.update({"X-MBX-APIKEY": self.settings.api_key})

        return session

    def _get_signature(self, params: ParamsDict):
        return hmac.new(
            self.settings.secret_key.encode("utf-8"),
            urlencode(params).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def setup_weight(self):
        metadata = await self.get_metadata()

        logger.debug(f"weight setup: {metadata.weights}")

        self.weights = metadata.weights
        self._next_weight_reset = None

    async def add_weight(self, weight):
        if (
            self.weights + weight + 1
        ).amount >= self.api_weight_threshold and not self._next_weight_reset:
            metadata = await self.get_metadata()

            self.weights = metadata.weights

            if (self.weights + weight).amount >= self.api_weight_threshold:
                binance_weight_reset_delta = (metadata.server_time + timedelta(minutes=1)).replace(
                    second=0, microsecond=0
                ) - metadata.server_time

                self._next_weight_reset = datetime.now() + binance_weight_reset_delta

        elif self._next_weight_reset:
            to_wait = (self._next_weight_reset - datetime.now() + timedelta(seconds=2)).total_seconds()

            self.weights.reset()

            logger.debug(f"weight threshold reached ({self.api_weight_threshold}), sleep and reset")

            if to_wait > 0:
                sleep(to_wait)

            self._next_weight_reset = None

        self.weights += weight

    async def get_account_info(self):
        params = {"timestamp": datetime.now().strftime("%s000")}

        params["signature"] = self._get_signature(params)

        await self.add_weight(10)

        async with await self.get_session() as session:
            response = await session.get(f"{self.settings.api_url}/api/v3/account", params=params)

            return await response.json()

    async def create_order(
        self,
        symbol: str,
        side: str,
        type: str,
        price: float = 0.0,
        quantity: float = 0.0,
        quote_quantity: float = 0.0,
        stop_price: float = 0.0,
        time_in_force: str = "",
        real: bool = False,
    ):
        params: ParamsDict = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "timestamp": datetime.now().strftime("%s000"),
        }

        if quantity:
            params["quantity"] = quantity
        elif quote_quantity:
            params["quoteOrderQty"] = quote_quantity
        else:
            raise Exception("Quantity must be set")

        if time_in_force:
            params["timeInForce"] = time_in_force

        if price:
            params["price"] = price
        if stop_price:
            params["stopPrice"] = stop_price

        params["signature"] = self._get_signature(params)

        await self.add_weight(1)

        async with await self.get_session() as session:
            if not real:
                response = await session.post(f"{self.settings.api_url}/api/v3/order/test", params=params)
            else:
                response = await session.post(f"{self.settings.api_url}/api/v3/order", params=params)

        json_data = await response.json()

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"create order: sending {json.dumps(params, indent=4)}")
            logger.debug(f"create order: get {json.dumps(json_data, indent=4)}")

        return json_data

    async def get_order(self, symbol: str, order_id: int):
        params: ParamsDict = {
            "symbol": symbol,
            "orderId": order_id,
            "timestamp": datetime.now().strftime("%s000"),
        }
        params["signature"] = self._get_signature(params)

        await self.add_weight(2)

        async with await self.get_session() as session:
            response = await session.get(self.settings.api_url + "/api/v3/order", params=params)

        return await response.json()

    async def list_orders(self, symbol: str):
        params: ParamsDict = {"symbol": symbol, "timestamp": datetime.now().strftime("%s000")}
        params["signature"] = self._get_signature(params)

        await self.add_weight(10)

        async with await self.get_session() as session:
            response = await session.get(self.settings.api_url + "/api/v3/allOrders", params=params)

        return await response.json()

    async def cancel_order(self, symbol: str, order_id: int):
        params: ParamsDict = {
            "symbol": symbol,
            "orderId": order_id,
            "timestamp": datetime.now().strftime("%s000"),
        }
        params["signature"] = self._get_signature(params)

        await self.add_weight(1)

        async with await self.get_session() as session:
            response = await session.delete(self.settings.api_url + "/api/v3/order", params=params)

        return await response.json()

    async def get_exchange_info(self):
        await self.add_weight(10)

        async with await self.get_session() as session:
            response = await session.get(f"{self.settings.api_url}/api/v3/exchangeInfo")

            return await response.json()

    async def get_metadata(self):
        async with await self.get_session() as session:
            response = await session.get(f"{self.settings.api_url}/api/v3/time")

            data = await response.json()

        return BinanceMetadata(
            server_time=data.get("serverTime"),
            weights={k: v for k, v in response.headers.items() if k.startswith("x-mbx-used")},
        )

    async def get_prices(self) -> dict:
        await self.add_weight(2)

        async with await self.get_session() as session:
            response = await session.get(f"{self.settings.api_url}/api/v3/ticker/bookTicker")

            return await response.json()

    #
    # User Data Streams methods
    # to setup account/balance/order update streams
    #

    async def request_listen_key(self) -> str:
        await self.add_weight(1)

        async with await self.get_session() as session:
            response = await session.post(f"{self.settings.api_url}/api/v3/userDataStream")

            return (await response.json())["listenKey"]

    async def keep_alive_listen_key(self, listen_key: str) -> str:
        await self.add_weight(1)

        async with await self.get_session() as session:
            response = await session.put(
                f"{self.settings.api_url}/api/v3/userDataStream", params={"listenKey": listen_key}
            )

            return await response.json()

    async def close_listen_key(self, listen_key: str) -> str:
        await self.add_weight(1)

        async with await self.get_session() as session:
            response = await session.delete(
                f"{self.settings.api_url}/api/v3/userDataStream", params={"listenKey": listen_key}
            )

            return await response.json()

    def _get_shift_delta(self, interval: str) -> timedelta:
        unit_value, interval_unit = interval[:-1], interval[-1]

        if interval == "1M":
            return timedelta(days=30)
        elif interval == "1w":
            return timedelta(weeks=1)
        elif interval_unit == "d":
            return timedelta(days=int(unit_value))
        elif interval_unit == "h":
            return timedelta(hours=int(unit_value))
        elif interval_unit == "m":
            return timedelta(minutes=int(unit_value))

        raise InvalidInterval(interval)

    async def get_order_book(self, symbol: str):
        async with await self.get_session() as session:
            await self.add_weight(1)

            response = await session.get(
                f"{self.settings.api_url}/api/v3/depth", params={"symbol": symbol}
            )

            return await response.json()

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str = "1d",
        start_datetime: datetime = datetime(2000, 1, 1),
        end_datetime: datetime = datetime.now(),
    ) -> DataFrame:
        if start_datetime < datetime(2000, 1, 1):
            raise WrongDatetimeRange(start_datetime)
        elif end_datetime < datetime(2000, 1, 1):
            raise WrongDatetimeRange(end_datetime)
        elif interval not in self.api_possible_intervals:
            raise InvalidInterval(interval)

        shift_delta = self._get_shift_delta(interval)

        start_datetime -= shift_delta
        end_datetime -= shift_delta

        klines = []
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(start_datetime.strftime("%s")) * 1000,
            "endTime": int(end_datetime.strftime("%s")) * 1000,
            "limit": 1000,
        }

        async with await self.get_session() as session:
            while True:
                await self.add_weight(1)

                response = await session.get(f"{self.settings.api_url}/api/v3/klines", params=params)
                klines_part = await response.json()

                if klines_part == []:
                    break

                if not isinstance(klines_part, list):
                    raise BinanceError(klines_part)

                klines += klines_part

                if datetime.fromtimestamp((klines_part[-1][0]) / 1000) >= end_datetime:
                    break

                params["startTime"] = klines_part[-1][0] + 1000

        df = DataFrame(
            [
                {
                    "timestamp": datetime.fromtimestamp((kline_data[6] + 1) / 1000),
                    "open": float(kline_data[1]),
                    "high": float(kline_data[2]),
                    "low": float(kline_data[3]),
                    "close": float(kline_data[4]),
                    "volumes": float(kline_data[5]),
                    "trades": kline_data[8],
                }
                for kline_data in klines
            ]
        )

        if not df.empty:
            df["timestamp"] = DatetimeIndex(df["timestamp"])
            df.set_index("timestamp", inplace=True)

            if interval == "1d":
                df = df.resample("D").mean()
                df.index.freq = None

        return df


""" TODO remove if not used 09/2022
class Kline(BaseModel):
    symbol: str
    time: datetime
    next: datetime
    open: float
    high: float
    low: float
    close: float
    complete: bool

    @root_validator(pre=True)
    def extract_values(cls, v):
        return {
            "time": v["E"] // 1000,
            "next": v["k"]["T"] // 1000,
            "symbol": v["s"],
            "open": v["k"]["o"],
            "high": v["k"]["h"],
            "low": v["k"]["l"],
            "close": v["k"]["c"],
            "complete": v["k"]["x"],
        }


class Ticker(BaseModel):
    timestamp: datetime
    symbol: str
    last_price: float
    best_ask_price: float
    best_ask_quantity: float
    best_bid_price: float
    best_bid_quantity: float
    trades: int

    @root_validator(pre=True)
    def extract_values(cls, v):
        return {
            "timestamp": datetime.fromtimestamp(v["E"] // 1000),
            "symbol": v["s"],
            "last_price": v["c"],
            "best_ask_price": v["a"],
            "best_ask_quantity": v["A"],
            "best_bid_price": v["b"],
            "best_bid_quantity": v["B"],
            "trades": v["n"],
        }
"""


class BinanceWebSocketAdapter:
    def __init__(self, settings):
        self.settings = settings

    async def open(self, endpoint: str):
        return await websockets.connect(endpoint)  # type: ignore

    async def close(self, session):
        await session.close()

    async def send(self, session, data: dict):
        await session.send(json.dumps(data))

    async def receive(self, session, timeout: Optional[int] = 1) -> Optional[Dict]:
        try:
            data = await asyncio.wait_for(session.recv(), timeout=timeout)

            return json.loads(data)
        except asyncio.TimeoutError:
            return None


class BinanceMarketWebSocketAdapter(BinanceWebSocketAdapter):
    def __init__(self, *args, **kwargs):
        super(BinanceMarketWebSocketAdapter, self).__init__(*args, **kwargs)

        self.subscriptions = set()

    async def open(self):
        session = await super().open(self.settings.stream_url)

        self.subscriptions = set()

        return session

    async def reopen(self):
        current_subscriptions = self.subscriptions

        session = await self.open()

        await self.subscribe(session, current_subscriptions)

        return session

    async def close(self, session):
        await super().close(session)

        self.subscriptions = set()

    async def request_subscriptions_list(self, session):
        await self.send(session, {"method": "LIST_SUBSCRIPTIONS", "id": 3})

    async def subscribe(self, session, streams: List[str]):
        subscribe_to = []

        for stream in streams:
            if stream not in self.subscriptions and len(self.subscriptions) < 1000:
                subscribe_to.append(stream)

                self.subscriptions.add(stream)

        if subscribe_to:
            await self.send(session, {"method": "SUBSCRIBE", "params": subscribe_to, "id": 1})

    async def unsubscribe(self, session, streams: List[str]):
        unsubscribe_to = []

        for stream in streams:
            if stream in self.subscriptions:
                unsubscribe_to.append(stream)

                self.subscriptions.remove(stream)

        if unsubscribe_to:
            await self.send(session, {"method": "UNSUBSCRIBE", "params": unsubscribe_to, "id": 312})


class BinanceUserDataWebSocketAdapter(BinanceWebSocketAdapter):
    def __init__(self, *args, **kwargs):
        super(BinanceUserDataWebSocketAdapter, self).__init__(*args, **kwargs)

        self.listen_key = None

    async def open(self, listen_key: str):
        session = await super().open(self.settings.stream_url + f"?streams={listen_key}")

        self.listen_key = listen_key

        return session
