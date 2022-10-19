from typing import List, Optional

from analyst.bot.strategies.base import Strategy
from analyst.controllers.factory import Controllers
from analyst.crypto.models import Order


async def enrich_order_repository(
    controllers: Controllers, symbol: str, strategy: Optional[Strategy] = None
) -> List[Order]:
    orders = await controllers.binance.list_orders(symbol="AMPBTC")

    for order in orders:
        await controllers.mongo.store_order(order, strategy)

    return orders
