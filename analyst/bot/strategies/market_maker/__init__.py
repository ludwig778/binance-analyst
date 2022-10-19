from typing import Any

from analyst.bot.strategies.market_maker.v1 import MarketMakerV1  # type: ignore
from analyst.bot.strategies.market_maker.v2 import MarketMakerV2  # type: ignore
from analyst.bot.strategies.market_maker.v3 import MarketMakerV3

__all__: Any = [
    MarketMakerV1,
    MarketMakerV2,
    MarketMakerV3,
]
