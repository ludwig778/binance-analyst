import hashlib
import hmac

import requests
from cachetools import TTLCache, cached


class BinanceAdapter:
    def __init__(self, settings):
        self.settings = settings

        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.settings.api_key})

    def get_account_info(self):
        server_time = self.get_time()
        params = f"timestamp={server_time}"

        signature = hmac.new(
            self.settings.secret_key.encode("utf-8"), params.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        response = self.session.get(
            f"{self.settings.api_url}/api/v3/account",
            params={"timestamp": server_time, "signature": signature},
        )

        return response.json()

    def ping(self):
        return self.session.get(f"{self.settings.api_url}/api/v3/ping").json()

    @cached(cache=TTLCache(maxsize=1, ttl=600))
    def get_exchange_info(self):
        return self.session.get(f"{self.settings.api_url}/api/v3/exchangeInfo").json().get("symbols")

    def get_time(self):
        return self.session.get(f"{self.settings.api_url}/api/v3/time").json().get("serverTime")

    def weight(self):
        return {
            k: v
            for k, v in self.session.get(f"{self.settings.api_url}/api/v3/ping").headers.items()
            if k.startswith("x-mbx-used")
        }

    @cached(cache=TTLCache(maxsize=1, ttl=600))
    def get_prices(self):
        return {
            ticker.get("symbol"): {
                "ask": float(ticker.get("askPrice")),
                "bid": float(ticker.get("bidPrice")),
            }
            for ticker in self.session.get(f"{self.settings.api_url}/api/v3/ticker/bookTicker").json()
        }

    def get_historical_klines(self, symbol, interval, limit=1000):
        return self.session.get(
            f"{self.settings.api_url}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        ).json()
