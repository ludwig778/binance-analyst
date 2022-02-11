from datetime import datetime
from pprint import pprint as pp
from time import sleep

import pandas as pd

from app.backend.binance import binance
from app.binance.account import *
from app.core.settings import settings
from app.helpers import *

t1 = datetime.now()
# pp(dict(settings))


# pp(binance)
# pp(binance.ping())
# pp(binance.get_prices())
# pp(binance.weight())
# pp(binance.get_account_info())


pp(Account.load().__dict__)
btc = Coin("BTC")
eth = Coin("ETH")
print()
pp([btc, eth])

print()

pp(btc.to(eth))
# pp(btc.to(eth).get_klines())
# pp(binance.get_prices())


base_pairs = PairsManager.load()
# pairs = PairsManager.filter(pairs, ["BTC", "ETH"])
pairs = PairsManager.filter(base_pairs, ["BTC", "BNB", "LTC", "BAT", "ETH"], exclusive=True)
print(list(pairs.keys()) + [len(pairs)])
dfs = PairsManager.load_dataframes(pairs)
print(pairs.keys())
"""
i = 6
t1 = datetime.now()
pairs = Pairs.load()
klines = pairs.load_klines(workers=i)
t2 = datetime.now()
tdiff = t2 - t1
print(f"Workers #{i:2d} : {tdiff.seconds}.{tdiff.microseconds}")
"""


print(dfs.get("LTCBTC"))
print(filter_dataframes(dfs))

print()


t2 = datetime.now()
tdiff = t2 - t1
print(f"Took : {tdiff.seconds}.{tdiff.microseconds} seconds")

print()
