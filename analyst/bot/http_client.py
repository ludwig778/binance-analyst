import traceback
from decimal import Decimal
from typing import Dict, List

from aiohttp import ClientResponseError, ClientSession, ServerDisconnectedError

from analyst.bot.strategies.base import Strategy
from analyst.crypto.models import Order
from analyst.repositories.strategy import StrategyRepository
from analyst.repositories.utils import serialize_obj


class BotHttpClient:
    def __init__(self, settings):
        self.settings = settings

        self._token = None

    def _get_url(self, path):
        return f"http://{self.settings.client_host}:{self.settings.client_port}{path}"

    async def _request(self, session, method, url, *args, headers=None, **kwargs):
        if self._token:
            if not headers:
                headers = {}

            headers["Authorization"] = f"Bearer {self._token}"

        response = await session.request(method, self._get_url(url), *args, headers=headers, **kwargs)
        response.raise_for_status()

        return await response.json()

    async def login(self):
        async with ClientSession() as session:
            response = await self._request(
                session, "post", "/login", data={"password": self.settings.jwt_secret}
            )

            self._token = response["token"]

    async def request(self, method, url, *args, **kwargs):
        async with ClientSession() as session:
            try:
                return await self._request(session, method, url, *args, **kwargs)
            except ServerDisconnectedError:
                await self.login()
            except ClientResponseError as exc:
                if exc.code in (400, 401):
                    await self.login()
                else:
                    raise exc

            return await self._request(session, method, url, *args, **kwargs)

    async def ping(self):
        return await self.request("get", "/ping")

    async def get_running_strategies(self) -> Dict[Strategy, List[Order]]:
        strategies_data = await self.request("get", "/strategies/running")
        strategies = {}

        for strategy_data in strategies_data:
            strategy = StrategyRepository._create_strategy(strategy_data)
            orders = [Order(**order_data) for order_data in strategy_data["orders"]]

            strategies[strategy] = orders

        return strategies

    async def test(self):
        return await self.request("get", "/test")

    async def add_strategy(self, name, version, args):
        try:
            return await self.request(
                "post",
                "/strategies/add",
                json={"name": name, "version": version, "args": serialize_obj(args)},
            )
        except Exception:
            print(traceback.format_exc())

    async def stop_strategy(self, strategy: Strategy):
        return await self.request("post", "/strategies/stop", json={"id": str(strategy.id)})

    async def remove_strategy(self, strategy: Strategy):
        return await self.request("post", "/strategies/remove", json={"id": str(strategy.id)})

    async def get_account(self):
        raw_account = await self.request("get", "/account")

        account = []

        for data in raw_account:
            account.append(
                {
                    "symbol": data["symbol"],
                    "quantity": Decimal(data["quantity"]) if data["quantity"] else None,
                    "usdt": Decimal(data["usdt"]) if data["usdt"] else None,
                }
            )

        return account

    async def get_pairs(self):
        return await self.request("get", "/pairs")
