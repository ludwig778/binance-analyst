import asyncio
import logging

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientResponseError
from pytest import fixture, raises

from analyst.bot.http_server import BotHttpServer

logging.getLogger("asyncio").setLevel(logging.WARNING)


@fixture(scope="function")
async def setup_bot_http_server(settings, controllers):
    http_server = BotHttpServer(settings=settings.bot, bot=None, controllers=controllers)
    await http_server.run()

    yield

    await http_server.stop()


async def test_bot_http_server_login(settings, setup_bot_http_server):
    async with ClientSession() as session:
        response = await session.post(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
            data={"password": settings.bot.jwt_secret},
        )

        data = await response.json()

        assert data["token"]


async def test_bot_http_server_login_exception(settings, setup_bot_http_server):
    async with ClientSession() as session:
        with raises(ClientResponseError, match="Wrong password"):
            response = await session.post(
                f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
                data={"password": settings.bot.jwt_secret + "_false"},
            )
            response.raise_for_status()


async def test_bot_http_server_ping(settings, setup_bot_http_server):
    async with ClientSession() as session:
        response = await session.get(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/ping",
            data={"password": settings.bot.jwt_secret},
        )

        data = await response.json()

        assert data["status"] == "pong"


async def test_bot_http_server_get_user(settings, setup_bot_http_server):
    async with ClientSession() as session:
        response = await session.post(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
            data={"password": settings.bot.jwt_secret},
        )

        token = (await response.json())["token"]

        response = await session.get(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/user",
            headers={"Authorization": f"Bearer {token}"},
        )

        data = await response.json()

        assert data["exp"]


async def test_bot_http_server_get_user_exception_missing_header(settings, setup_bot_http_server):
    async with ClientSession() as session:
        response = await session.post(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
            data={"password": settings.bot.jwt_secret},
        )

        with raises(ClientResponseError, match="Token is missing"):
            response = await session.get(
                f"http://{settings.bot.server_host}:{settings.bot.server_port}/user"
            )
            response.raise_for_status()


async def test_bot_http_server_get_user_exception_wrong_token(settings, setup_bot_http_server):
    async with ClientSession() as session:
        response = await session.post(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
            data={"password": settings.bot.jwt_secret},
        )

        with raises(ClientResponseError, match="Token is invalid"):
            response = await session.get(
                f"http://{settings.bot.server_host}:{settings.bot.server_port}/user",
                headers={"Authorization": "Bearer wrong_token"},
            )
            response.raise_for_status()


async def test_bot_http_server_jwt_token_expiring(settings, controllers):
    settings.bot.jwt_expire_delta_seconds = 1

    http_server = BotHttpServer(settings=settings.bot, bot=None, controllers=controllers)

    await http_server.run()

    async with ClientSession() as session:
        response = await session.post(
            f"http://{settings.bot.server_host}:{settings.bot.server_port}/login",
            data={"password": settings.bot.jwt_secret},
        )

        token = (await response.json())["token"]

        await asyncio.sleep(2)

        with raises(ClientResponseError, match="Token is expired"):
            response = await session.get(
                f"http://{settings.bot.server_host}:{settings.bot.server_port}/user",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()

    await http_server.stop()
