from typing import Dict

from pandas import DataFrame

from binance_analyst.models import Pair


Pairs = Dict[str, Pair]
PairsDataframes = Dict[str, DataFrame]
