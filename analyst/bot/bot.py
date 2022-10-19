from __future__ import annotations

import asyncio
import json
import traceback
from collections import defaultdict
from logging import getLogger
from typing import Any, Coroutine, Dict, List, Optional, Set, Tuple, Union
from uuid import UUID

from analyst.adapters.factory import get_adapters
from analyst.bot.exceptions import StrategyExit, StrategyHalt
from analyst.bot.http_server import BotHttpServer
from analyst.bot.order_manager import OrderManager
from analyst.bot.strategies.base import Strategy, StrategyState
from analyst.controllers.factory import Controllers, get_controllers
from analyst.crypto.models import Order, OrderFromUserDataStream, OutboundAccountPosition
from analyst.repositories.factory import get_repositories
from analyst.repositories.strategy import StrategyRepository
from analyst.repositories.utils import serialize_order_obj
from analyst.settings import get_settings

logger = getLogger("bot")


class Runner:
    def __init__(
        self,
        controllers: Controllers,
        order_manager: OrderManager,
    ):
        self.controllers = controllers
        self.order_manager = order_manager

        self.strategies: Dict[UUID, Strategy] = {}
        self.strategies_by_streams: Dict[str, Set[Strategy]] = defaultdict(set)

    async def setup(self):
        strategies = await self.controllers.mongo.get_running_strategies()

        for strategy in strategies:
            self.setup_strategy(strategy)

            await strategy.setup(self.order_manager)

    def setup_strategy(self, strategy):
        self.strategies[strategy.id] = strategy

        for stream_name in strategy.get_stream_names():
            self.strategies_by_streams[stream_name].add(strategy)

    def purge_strategy(self, strategy):
        del self.strategies[strategy.id]

        for stream_name in strategy.get_stream_names():
            self.strategies_by_streams[stream_name].remove(strategy)

            if not self.strategies_by_streams[stream_name]:
                del self.strategies_by_streams[stream_name]

    async def add_strategy(self, name, version, args) -> Tuple[bool, str]:
        # logger.info([name, version, args])
        try:
            strategy = StrategyRepository._create_strategy(
                {"name": name, "version": version, "args": args}
            )
            strategy.gatekeeping(self.order_manager)
            strategy.state = StrategyState.running

            await strategy.setup(self.order_manager)

            await self.controllers.mongo.store_strategy(strategy)

            self.setup_strategy(strategy)

            await self.controllers.binance.subscribe(strategy.get_stream_names())

            return True, ""
        except Exception as exc:
            logger.info("Error on Add Strategy")
            logger.info(traceback.format_exc())

            return False, str(exc)

    async def stop_strategy(self, strategy_id) -> Tuple[bool, str]:
        strategy = self.strategies.get(strategy_id)

        if not strategy:
            return False, "Could not find strategy"

        try:
            if strategy.state != StrategyState.running:
                return True, f"Nothing to do, state is {strategy.state.name}"

            strategy.state = StrategyState.stopping

            await self.controllers.mongo.store_strategy(strategy)

            return True, ""
        except Exception as exc:
            # logger.info("Error on Stop Strategy")
            # logger.info(traceback.format_exc())

            return False, str(exc)

    async def remove_strategy(self, strategy_id) -> Tuple[bool, str]:
        strategy = self.strategies.get(strategy_id)

        if not strategy:
            return False, "Could not find strategy"

        try:
            await self.controllers.mongo.delete_strategy(strategy)

            self.purge_strategy(strategy)

            await self.controllers.binance.unsubscribe(strategy.get_stream_names())

            return True, ""
        except Exception as exc:
            # logger.info("Error on Remove Strategy")
            # logger.info(traceback.format_exc())

            return False, str(exc)

    async def run_market_streams(self):
        streams = list(self.strategies_by_streams.keys())

        async for stream_name, ticker_data in self.controllers.binance.listen_market_streams(
            streams=streams
        ):
            stream_strategies = self.strategies_by_streams.get(stream_name)

            logger.debug(
                f"ticker symbol={ticker_data.symbol} "
                f"bid={ticker_data.bid_quantity:,.8f} @ {ticker_data.bid_price:,.8f} "
                f"ask={ticker_data.ask_quantity:,.8f} @ {ticker_data.ask_price:,.8f}"
            )

            if not stream_strategies:
                continue

            for strategy in list(stream_strategies):
                try:
                    async with strategy.lock:
                        await strategy.process_ticker_data(ticker_data, self.order_manager)
                except StrategyExit:
                    await strategy.terminate(self.order_manager)

                    self.purge_strategy(strategy)
                except StrategyHalt:
                    await strategy.stop(self.order_manager)

                    self.purge_strategy(strategy)

    async def keep_alive_user_data_stream(self):
        while True:
            await asyncio.sleep(30 * 60)

            await self.controllers.binance.update_user_data_stream()

    async def on_user_data_stream_restart(self):
        logger.info("user data stream restart")

        orders = await self.order_manager.get_updated_orders()

        logger.info(f"updated orders: got {len(orders)}")

        for order in orders:
            logger.debug(f"updated order: {json.dumps(serialize_order_obj(order.dict()))}")

            await self.process_order_to_strategy(order)

        await self.order_manager.setup()

    async def process_order_to_strategy(self, order: Order, update: bool = False):
        logger.info("process order to strategy")

        if not order.strategy_id:
            logger.info(f"no strategy_id found for order {order.internal_id}")

            return

        strategy = self.strategies.get(order.strategy_id)

        if not strategy:
            logger.info(f"no strategy_id={order.strategy_id} found")

            return

        async with strategy.lock:
            if update:
                order = await self.order_manager.update_order(order, strategy)

            try:
                await strategy.process_order(order, self.order_manager)

            except StrategyExit:
                await strategy.terminate(self.order_manager)

                self.purge_strategy(strategy)
            except StrategyHalt:
                await strategy.stop(self.order_manager)

                self.purge_strategy(strategy)

    async def run_user_data_stream(self):
        async for msg in self.controllers.binance.listen_user_data_stream(
            on_restart=self.on_user_data_stream_restart
        ):
            asyncio.create_task(self.on_user_data_message_received(msg))

    async def on_user_data_message_received(
        self, msg: Union[OrderFromUserDataStream, OutboundAccountPosition, Any]
    ):
        if isinstance(msg, OrderFromUserDataStream):
            # balances user data streams always comes after ~0.01s after the order update,
            # so the account is synced
            logger.debug("received order from user data stream: pre sleep")

            await asyncio.sleep(0.1)

            logger.info("received order from user data stream")
            logger.debug(json.dumps(serialize_order_obj(msg.dict())))

            received_order = msg

            stored_order = await self.controllers.mongo.get_order(
                received_order.id, received_order.symbol
            )

            if not stored_order:
                logger.warning(f"no order found for order {received_order.id} on {received_order.symbol}")

                return

            elif not stored_order.strategy_id:
                logger.warning(
                    f"no strategy_id set for order {received_order.id} on {received_order.symbol}"
                )

                return

            received_order.strategy_id = stored_order.strategy_id

            await self.process_order_to_strategy(received_order, update=True)

        elif isinstance(msg, OutboundAccountPosition):
            logger.info("received balances from user data stream")

            self.order_manager.update_account_with_live_data(msg)

        else:
            logger.debug("received unhandled from user data stream")

    async def run(self, extra_coroutines: Optional[List[Coroutine]] = None):
        logger.info("bot setup")

        await self.setup()
        await self.controllers.binance.open_streams()

        coroutines = [
            self.run_market_streams(),
            self.run_user_data_stream(),
            self.keep_alive_user_data_stream(),
        ]

        if extra_coroutines:
            coroutines += extra_coroutines

        logger.info("bot running")

        await asyncio.gather(*coroutines)

        logger.info("bot exit")


async def main():
    settings = get_settings()
    adapters = await get_adapters(settings=settings)
    repositories = get_repositories(settings=settings, adapters=adapters)
    controllers = get_controllers(adapters=adapters, repositories=repositories)

    order_manager = OrderManager(controllers=controllers)
    await order_manager.setup()

    runner = Runner(controllers=controllers, order_manager=order_manager)
    http_server = BotHttpServer(settings.bot, runner, controllers)
    # HIGH   QLCBTC VIBBTC
    # MED    TCTBTC DGBBTC
    # LOW    QKCBTC AMPBTC

    try:
        await asyncio.gather(runner.run(), http_server.run())
    except KeyboardInterrupt:
        await controllers.binance.close_streams()


if __name__ == "__main__":
    asyncio.run(main())
    # thread = Thread(target=runner.run)
    # thread.start()
