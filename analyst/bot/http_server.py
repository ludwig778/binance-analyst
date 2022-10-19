import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from uuid import UUID

import jwt
from aiohttp import web
from aiohttp.web_exceptions import HTTPBadRequest, HTTPUnauthorized

from analyst.bot.strategies.base import StrategyFlags, StrategyState
from analyst.controllers.factory import Controllers
from analyst.settings import BotSettings


class CustomEncoder(json.JSONEncoder):
    def default(cls, obj):
        if isinstance(obj, UUID):
            return str(obj)

        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, StrategyState):
            return obj.value
        elif isinstance(obj, StrategyFlags):
            return int(obj)
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, set):
            return list(obj)

        return json.JSONEncoder.default(cls, obj)


custom_dumps = partial(json.dumps, cls=CustomEncoder)


class BotHttpServer:
    def __init__(self, settings: BotSettings, bot, controllers: Controllers):
        self.settings = settings
        self.bot = bot
        self.controllers = controllers

    async def login(self, request):
        post_data = await request.post()

        if post_data["password"] != self.settings.jwt_secret:
            raise HTTPUnauthorized(reason="Wrong password")

        payload = {"exp": datetime.utcnow() + timedelta(seconds=self.settings.jwt_expire_delta_seconds)}
        jwt_token = jwt.encode(payload, self.settings.jwt_secret, self.settings.jwt_algorithm)

        return web.json_response({"token": jwt_token})

    async def check_logged(self, request):
        jwt_token = request.headers.get("authorization", None)

        if jwt_token:
            if "Bearer " not in jwt_token:
                raise HTTPUnauthorized(reason="Token is malformed")

            jwt_token = jwt_token.replace("Bearer ", "")

            try:
                payload = jwt.decode(
                    jwt_token, self.settings.jwt_secret, algorithms=[self.settings.jwt_algorithm]
                )

                return payload

            except jwt.DecodeError:
                raise HTTPUnauthorized(reason="Token is invalid")
            except jwt.ExpiredSignatureError:
                raise HTTPUnauthorized(reason="Token is expired")

        else:
            raise HTTPBadRequest(reason="Token is missing")

    async def get_user_metadata(self, request):
        payload = await self.check_logged(request)

        return web.json_response(payload)

    async def ping(self, request):
        return web.json_response({"status": "pong"})

    async def running_strategies(self, request):
        await self.check_logged(request)

        strategies = await self.controllers.mongo.get_running_strategies()
        strategies_data = []

        for strategy in strategies:
            strategy_data = strategy.dict()

            strategy_data["orders"] = [
                order.dict() for order in await self.controllers.mongo.get_strategy_orders(strategy)
            ]

            strategies_data.append(strategy_data)

        return web.json_response(strategies_data, dumps=custom_dumps)

    @staticmethod
    def _format_response(ok, message):
        response = {"status": "ok" if ok else "nok"}

        if message:
            response["message"] = message

        return response

    async def add_strategy(self, request):
        await self.check_logged(request)

        data = await request.json()
        ok, message = await self.bot.add_strategy(**data)

        return web.json_response(self._format_response(ok, message))

    async def stop_strategy(self, request):
        await self.check_logged(request)

        data = await request.json()
        ok, message = await self.bot.stop_strategy(UUID(data["id"]))

        return web.json_response(self._format_response(ok, message))

    async def remove_strategy(self, request):
        await self.check_logged(request)

        data = await request.json()
        ok, message = await self.bot.remove_strategy(UUID(data["id"]))

        return web.json_response(self._format_response(ok, message))

    async def get_account(self, request):
        await self.check_logged(request)

        account = self.bot.order_manager.account
        pairs = await self.bot.controllers.binance.load_pairs()

        converted_account = await self.bot.controllers.binance.convert_account_coins_to(
            account, to="USDT", pairs=pairs
        )

        formatted = [
            {
                "symbol": coin,
                "quantity": coin_amount.quantity,
                "usdt": converted_account.get(coin, None),
            }
            for coin, coin_amount in account.items()
        ]
        formatted = sorted(formatted, key=lambda x: x["usdt"], reverse=True)

        return web.json_response(formatted, dumps=custom_dumps)

    async def get_pairs(self, request):
        return web.json_response(list(self.bot.order_manager.pairs.keys()))

    async def test(self, request):
        await self.check_logged(request)

        return web.json_response({})

    async def run(self):
        self.app = web.Application()
        self.app.add_routes(
            [
                web.post("/login", self.login),
                web.get("/ping", self.ping),
                web.get("/user", self.get_user_metadata),
                web.get("/test", self.test),
                web.get("/account", self.get_account),
                web.get("/pairs", self.get_pairs),
                web.post("/strategies/add", self.add_strategy),
                web.post("/strategies/stop", self.stop_strategy),
                web.post("/strategies/remove", self.remove_strategy),
                web.get("/strategies/running", self.running_strategies),
            ]
        )
        runner = web.AppRunner(self.app)

        await runner.setup()

        self.site = web.TCPSite(runner, port=8000)

        await self.site.start()

    async def stop(self):
        await self.site.stop()
