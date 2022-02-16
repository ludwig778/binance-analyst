import hashlib
import hmac
from copy import deepcopy
from datetime import datetime, timedelta
from time import sleep

import requests
from cachetools import TTLCache, cached
from pydantic import BaseModel, Field

from binance_analyst.exceptions import BinanceError


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
                binance_weight_reset_delta = (
                    metadata.server_time + timedelta(minutes=1)
                ).replace(second=0, microsecond=0) - metadata.server_time

                self._next_weight_reset = datetime.now() + binance_weight_reset_delta

        elif self._next_weight_reset:
            to_wait = (
                self._next_weight_reset - datetime.now() + timedelta(seconds=2)
            ).total_seconds()

            self.weights.reset()

            sleep(to_wait)

            self._next_weight_reset = None

        self.weights += weight

    def get_account_info(self):
        self.add_weight(1)

        metadata = self.get_metadata()
        params = f"timestamp={metadata.server_time}"

        signature = hmac.new(
            self.settings.secret_key.encode("utf-8"),
            params.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.add_weight(10)

        response = self.session.get(
            f"{self.settings.api_url}/api/v3/account",
            params={"timestamp": metadata.server_time, "signature": signature},
        )

        return response.json()

    @cached(cache=TTLCache(maxsize=1, ttl=600))
    def get_exchange_info(self):
        self.add_weight(10)

        return (
            self.session.get(f"{self.settings.api_url}/api/v3/exchangeInfo")
            .json()
            .get("symbols")
        )

    def get_metadata(self):
        response = self.session.get(f"{self.settings.api_url}/api/v3/time")

        return BinanceMetadata(
            server_time=response.json().get("serverTime"),
            weights={
                k: v for k, v in response.headers.items() if k.startswith("x-mbx-used")
            },
        )

    def get_time(self):
        self.add_weight(1)

        return self._get_time()

    @cached(cache=TTLCache(maxsize=1, ttl=600))
    def get_prices(self):
        self.add_weight(2)

        return {
            ticker.get("symbol"): {
                "ask": float(ticker.get("askPrice")),
                "bid": float(ticker.get("bidPrice")),
            }
            for ticker in self.session.get(
                f"{self.settings.api_url}/api/v3/ticker/bookTicker"
            ).json()
        }

    def get_historical_klines(
        self,
        symbol: str,
        interval: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ):
        data = []
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": int(start_datetime.strftime("%s")) * 1000,
            "endTime": int(end_datetime.strftime("%s")) * 1000,
            "limit": 1000,
        }

        while True:
            self.add_weight(1)
            data_part = self.session.get(
                f"{self.settings.api_url}/api/v3/klines", params=params
            ).json()

            if data_part == []:
                break

            if not isinstance(data_part, list):
                raise BinanceError(data_part)

            data += data_part

            if datetime.fromtimestamp((data_part[-1][0]) / 1000) >= end_datetime:
                break

            params["startTime"] = data_part[-1][0] + 1000

        return data
