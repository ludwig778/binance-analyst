import asyncio
import json
import logging
import operator
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from typing import Callable, Dict, List, Optional, Set

from numpy import inf, nan
from pandas import DataFrame, concat, to_datetime
from websockets.exceptions import ConnectionClosed

from analyst.adapters.factory import Adapters
from analyst.crypto.exceptions import InvalidPairCoins, OrderWouldMatch
from analyst.crypto.models import (
    Account,
    CoinAmount,
    MarketStreamTicker,
    Order,
    OrderFromUserDataStream,
    OutboundAccountPosition,
    Pair,
    Pairs,
    TradeStreamObject,
)
from analyst.repositories.utils import serialize_account_obj

logger = getLogger("controllers.binance")


class BinanceController:
    def __init__(self, adapters: Adapters):
        self.adapters = adapters

        self.market_ws_session = None
        self.user_data_ws_session = None

    async def load_account(self) -> Account:
        account_info = await self.adapters.binance.get_account_info()

        coins = {}
        for coin in account_info.get("balances"):
            quantity = Decimal(coin.get("free", 0))

            if quantity:
                name = coin.get("asset")

                if name.startswith("LD"):
                    name = name.replace("LD", "")
                    continue

                coins[name] = CoinAmount(coin=name, quantity=quantity)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"load account: {json.dumps(serialize_account_obj(coins), indent=2)}")

        return coins

    async def load_pairs(self) -> Pairs:
        exchange_info, prices_list = await asyncio.gather(
            self.adapters.binance.get_exchange_info(), self.adapters.binance.get_prices()
        )

        prices_dict = {prices_data.get("symbol"): prices_data for prices_data in prices_list}

        pairs = {}
        for coin_data in exchange_info["symbols"]:
            symbol = coin_data.get("symbol")
            prices = prices_dict.get(symbol)

            if not prices:
                continue

            base_coin = coin_data.get("baseAsset")
            quote_coin = coin_data.get("quoteAsset")

            base_asset_precision = coin_data.get("baseAssetPrecision")
            quote_asset_precision = coin_data.get("quoteAssetPrecision")

            filters = {filter["filterType"]: filter for filter in coin_data.get("filters")}
            quote_min_amount = Decimal(filters["MIN_NOTIONAL"]["minNotional"])

            min_quantity = Decimal(filters["LOT_SIZE"]["minQty"])
            max_quantity = Decimal(filters["LOT_SIZE"]["maxQty"])
            step_size = Decimal(filters["LOT_SIZE"]["stepSize"])

            ask_price = prices.get("askPrice")
            bid_price = prices.get("bidPrice")

            ask_quantity = prices.get("askQty")
            bid_quantity = prices.get("bidQty")

            pairs[symbol] = Pair(
                base=base_coin,
                quote=quote_coin,
                quote_min_amount=quote_min_amount,
                base_asset_precision=base_asset_precision,
                quote_asset_precision=quote_asset_precision,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
                step_size=step_size,
                ask_price=ask_price,
                bid_price=bid_price,
                ask_quantity=ask_quantity,
                bid_quantity=bid_quantity,
            )

        logger.debug(f"loaded pairs: {len(pairs)}")

        return pairs

    @staticmethod
    def filter_pairs(pairs: Pairs, coin_strs: List[str], exclusive=False) -> Pairs:
        op = operator.__and__ if exclusive else operator.__or__

        return {
            symbol: pair
            for symbol, pair in pairs.items()
            if op(pair.base in coin_strs, pair.quote in coin_strs)
        }

    async def get_order_book(
        self,
        symbol: str,
    ) -> DataFrame:
        data = await self.adapters.binance.get_order_book(symbol)

        dfs = []

        for column_name in ("asks", "bids"):
            df = DataFrame(data[column_name], columns=("price", column_name))

            df.set_index("price", inplace=True)
            # df.sort_values("price", ascending=False, inplace=True)

            dfs.append(df)

        df = concat(dfs, axis=0)
        df.sort_values("price", ascending=False, inplace=True)

        df.index = df.index.astype(float)
        df = df.astype(float)

        return df

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        start_datetime: datetime = datetime(2000, 1, 1),
        end_datetime: datetime = datetime.now(),
    ) -> DataFrame:
        df = await self.adapters.binance.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        # Fix, trades are integers
        if not df.empty:
            df = df.replace([inf, -inf], nan).dropna()
            df["trades"] = df["trades"].astype(int)

        return df

    async def load_dataframes(self, pairs: Pairs, workers=5, **kwargs) -> DataFrame:
        logger.debug(f"load dataframes: fetching {len(pairs)} pairs...")
        start_time = datetime.now()

        semaphore = asyncio.Semaphore(workers)

        async def run(symbol: str):
            async with semaphore:
                return symbol, await self.get_klines(symbol, **kwargs)

        dataframes = dict(await asyncio.gather(*[run(symbol) for symbol in pairs.keys()]))

        dataframe = concat(dataframes, join="outer", axis=1)
        dataframe.index = to_datetime(dataframe.index)

        logger.info(
            f"load dataframes: fetching {len(pairs)} pairs took "
            f"{(datetime.now() - start_time).total_seconds():.2f} secs"
        )

        return dataframe

    async def create_test_order(self, symbol: str, side: str, type: str, **params) -> None:
        if "real" in params:
            del params["real"]

        data = await self.adapters.binance.create_order(symbol, side, type, real=False, **params)

        if "code" in data:
            raise Exception(f"{data['msg']}")

    async def create_order(self, symbol: str, side: str, type: str, **params) -> Order:
        data = await self.adapters.binance.create_order(symbol, side, type, real=True, **params)

        if "code" in data:
            if "msg" in data and data["msg"] == "Order would immediately match and take.":
                raise OrderWouldMatch()
            raise Exception(f"{data['msg']}")

        return await self.get_order(symbol, data["orderId"])

    async def get_order(self, symbol: str, order_id: int) -> Order:
        order_data = await self.adapters.binance.get_order(symbol, order_id)

        return Order(**order_data)

    async def list_orders(self, symbol: str) -> List[Order]:
        orders_data = await self.adapters.binance.list_orders(symbol)

        return [Order(**order_data) for order_data in orders_data]

    async def get_updated_order(self, order: Order) -> Order:
        return await self.get_order(order.symbol, order.id)

    async def cancel_order(self, order: Order) -> Order:
        await self.adapters.binance.cancel_order(order.symbol, order.id)

        return await self.get_order(order.symbol, order.id)

    async def convert_coin(self, asset: CoinAmount, to: str, pairs: Optional[Pairs] = None) -> CoinAmount:

        if pairs is None:
            pairs = await self.load_pairs()

        if pair := pairs.get(f"{asset.coin}{to}"):
            if pair.ask_price:
                return CoinAmount(coin=to, quantity=asset.quantity * pair.ask_price)

        if pair := pairs.get(f"{to}{asset.coin}"):
            if pair.bid_price:
                return CoinAmount(coin=to, quantity=asset.quantity / pair.bid_price)

        raise InvalidPairCoins(f"{asset.coin}-{to}")

    async def get_transitional_coins(
        self, origin: str, dest: str, pairs: Optional[Pairs] = None
    ) -> Set[str]:

        if pairs is None:
            pairs = await self.load_pairs()

        origin_candidates = set()
        dest_candidates = set()

        for symbol, pair in pairs.items():
            if origin in symbol and pair.ask_price and pair.bid_price:
                origin_candidates.add(symbol.replace(origin, ""))
            elif dest in symbol and pair.ask_price and pair.bid_price:
                dest_candidates.add(symbol.replace(dest, ""))

        return origin_candidates.intersection(dest_candidates)

    async def convert_transitional_coins(
        self, asset: CoinAmount, dest: str, pairs: Optional[Pairs] = None
    ) -> Dict[str, Decimal]:

        if pairs is None:
            pairs = await self.load_pairs()

        transitional_coins = await self.get_transitional_coins(asset.coin, dest, pairs=pairs)
        conversions = {}

        for coin in transitional_coins:
            try:
                transition = await self.convert_coin(asset, coin, pairs)
                dest_coin = await self.convert_coin(transition, dest, pairs)

                if dest_coin.quantity:
                    conversions[coin] = dest_coin.quantity
            except ZeroDivisionError:
                pass

        return conversions

    async def convert_account_coins_to(
        self, account: Account, to: str, pairs: Optional[Pairs] = None
    ) -> Dict[str, Decimal]:
        converted_coins = {}

        if pairs is None:
            pairs = await self.load_pairs()

        for asset in account.values():
            if asset.coin == to:
                converted_coins[asset.coin] = asset.quantity

            else:
                try:
                    converted = await self.convert_coin(asset, to, pairs)
                except InvalidPairCoins:
                    transitions = await self.get_transitional_coins(asset.coin, to, pairs)

                    transition_results = {}
                    for transition in transitions:
                        try:
                            converted = await self.convert_coin(
                                await self.convert_coin(asset, transition, pairs), to, pairs
                            )
                        except InvalidPairCoins:
                            continue
                        transition_results[transition] = converted

                    converted = sorted(transition_results.values(), key=lambda x: x.quantity)[-1]

                converted_coins[asset.coin] = converted.quantity

        return converted_coins

    async def listen_market_streams(
        self, streams: Optional[List[str]] = None, on_restart: Optional[Callable] = None
    ):
        logger.info("listen market stream")

        trigger_on_restart = False

        while 1:
            if trigger_on_restart and on_restart:
                try:
                    await self.open_market_stream()
                except ConnectionRefusedError:
                    logger.info("unable to connect to market stream")

                    await asyncio.sleep(5)

                    continue

                await on_restart()

                trigger_on_restart = False

            while 1:
                try:
                    data = await self.adapters.binance_market_websocket.receive(self.market_ws_session)

                    if not data or "stream" not in data:
                        continue

                    elif data["stream"].endswith("@trade"):
                        yield data["stream"], TradeStreamObject(**data["data"])

                    elif data["stream"].endswith("@ticker"):
                        yield data["stream"], MarketStreamTicker(**data["data"])

                except ConnectionClosed:
                    logger.info("connection to market stream closed")

                    trigger_on_restart = True

                    await asyncio.sleep(5)

                    break

    async def subscribe(self, streams: List[str]):
        logger.info(f"subscribing to {streams}")

        await self.adapters.binance_market_websocket.subscribe(self.market_ws_session, streams)

    async def unsubscribe(self, streams: List[str]):
        logger.info(f"unsubscribing to {streams}")

        await self.adapters.binance_market_websocket.unsubscribe(self.market_ws_session, streams)

    async def update_user_data_stream(self, listen_key: Optional[str] = None):
        listen_key = listen_key or self.adapters.binance_user_data_websocket.listen_key

        if not listen_key:
            raise Exception("Listen key must be provided")

        await self.adapters.binance.keep_alive_listen_key(listen_key)

    async def listen_user_data_stream(self, on_restart: Optional[Callable] = None):
        logger.info("listen user data stream")

        trigger_on_restart = False

        while 1:
            if trigger_on_restart and on_restart:
                try:
                    await self.open_user_data_stream()
                except ConnectionRefusedError:
                    logger.info("unable to connect to user data stream")

                    await asyncio.sleep(5)

                    continue

                await on_restart()

                trigger_on_restart = False

            while 1:
                try:
                    data = await self.adapters.binance_user_data_websocket.receive(
                        self.user_data_ws_session
                    )

                    if not data or "stream" not in data:
                        continue

                    elif data["data"]["e"] == "executionReport":
                        yield OrderFromUserDataStream(**data["data"])

                    elif data["data"]["e"] == "outboundAccountPosition":
                        yield OutboundAccountPosition(**data["data"])

                    else:
                        logger.debug("received unhandled message from user data stream")
                        logger.debug(json.dumps(data))

                except ConnectionClosed:
                    logger.info("connection to user data stream closed")

                    trigger_on_restart = True

                    await asyncio.sleep(5)

                    break

    async def open_market_stream(self, streams: Optional[List[str]] = None):
        if self.market_ws_session:
            logger.info("reopen market stream")

            self.market_ws_session = await self.adapters.binance_market_websocket.reopen()
        else:
            logger.info("open market stream")

            self.market_ws_session = await self.adapters.binance_market_websocket.open()

            if streams:
                await self.subscribe(streams)

    async def open_user_data_stream(self):
        logger.info("open user data stream")

        listen_key = await self.adapters.binance.request_listen_key()

        self.user_data_ws_session = await self.adapters.binance_user_data_websocket.open(listen_key)

    async def open_streams(self):
        logger.info("open streams")

        await asyncio.gather(self.open_market_stream(), self.open_user_data_stream())

    async def close_market_stream(self):
        logger.info("close market stream")

        if self.market_ws_session:
            await self.adapters.binance_market_websocket.close(self.market_ws_session)

    async def close_user_data_stream(self):
        logger.info("close user data stream")

        if self.user_data_ws_session:
            await self.adapters.binance_user_data_websocket.close(self.user_data_ws_session)

    async def close_streams(self):
        logger.info("close streams")

        await asyncio.gather(self.close_market_stream(), self.close_user_data_stream())
