import hashlib
import hmac
import json
from copy import deepcopy
from datetime import datetime, timedelta
from time import sleep
from typing import List
from urllib.parse import urlencode

import requests
from pandas import DataFrame, DatetimeIndex
from pydantic import BaseModel, Field, root_validator
from websocket import create_connection

from analyst.crypto.exceptions import BinanceError, InvalidInterval, WrongDatetimeRange


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

        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.settings.api_key})

        self.setup_weight()

    def setup_weight(self):
        metadata = self.get_metadata()

        self.weights = metadata.weights
        self._next_weight_reset = None

    def add_weight(self, weight):
        if (
            self.weights + weight + 1
        ).amount >= self.api_weight_threshold and not self._next_weight_reset:
            metadata = self.get_metadata()

            self.weights = metadata.weights

            if (self.weights + weight).amount >= self.api_weight_threshold:
                binance_weight_reset_delta = (metadata.server_time + timedelta(minutes=1)).replace(
                    second=0, microsecond=0
                ) - metadata.server_time

                self._next_weight_reset = datetime.now() + binance_weight_reset_delta

        elif self._next_weight_reset:
            to_wait = (self._next_weight_reset - datetime.now() + timedelta(seconds=2)).total_seconds()

            self.weights.reset()

            if to_wait > 0:
                sleep(to_wait)

            self._next_weight_reset = None

        self.weights += weight

    def _get_signature(self, params):
        return hmac.new(
            self.settings.secret_key.encode("utf-8"),
            urlencode(params).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def get_account_info(self):
        params = {"timestamp": datetime.now().strftime("%s000")}

        params["signature"] = self._get_signature(params)

        self.add_weight(10)

        response = self.session.get(f"{self.settings.api_url}/api/v3/account", params=params)

        return response.json()

    def get_exchange_info(self):
        self.add_weight(10)

        return self.session.get(f"{self.settings.api_url}/api/v3/exchangeInfo").json()

    def get_metadata(self):
        response = self.session.get(f"{self.settings.api_url}/api/v3/time")

        return BinanceMetadata(
            server_time=response.json().get("serverTime"),
            weights={k: v for k, v in response.headers.items() if k.startswith("x-mbx-used")},
        )

    def get_time(self):
        self.add_weight(1)

        return self._get_time()

    def get_prices(self) -> dict:
        self.add_weight(2)

        return self.session.get(f"{self.settings.api_url}/api/v3/ticker/bookTicker").json()

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

    def get_historical_klines(
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

        while True:
            self.add_weight(1)
            klines_part = self.session.get(
                f"{self.settings.api_url}/api/v3/klines", params=params
            ).json()

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


class BinanceWebSocketAdapter:
    endpoint = "wss://stream.binance.com:443/stream"

    def __init__(self):
        self.session = None
        self.subscriptions = set()

    def open(self):
        self.session = create_connection(self.endpoint)
        self.subscriptions = set()

    def close(self):
        self.session.close()
        self.subscriptions = set()

    def send(self, data: dict):
        self.session.send(json.dumps(data))

    def receive(self) -> dict:
        return json.loads(self.session.recv())

    def request_subscriptions_list(self):
        self.send({"method": "LIST_SUBSCRIPTIONS", "id": 3})

    def subscribe(self, streams: List[str]):
        subscribe_to = []

        for stream in streams:
            if stream not in self.subscriptions and len(self.subscriptions) < 1000:
                subscribe_to.append(stream)

                self.subscriptions.add(stream)

        if subscribe_to:
            print("SUB", subscribe_to)
            self.send({"method": "SUBSCRIBE", "params": subscribe_to, "id": 1})

    def unsubscribe(self, streams: List[str]):
        unsubscribe_to = []

        for stream in streams:
            if stream in self.subscriptions:
                unsubscribe_to.append(stream)

                self.subscriptions.remove(stream)

        if unsubscribe_to:
            self.send({"method": "UNSUBSCRIBE", "params": unsubscribe_to, "id": 312})

    def listen(self):
        while True:
            data = self.receive()

            # if data.get("id") == 3:
            #    print(data)

            yield data
