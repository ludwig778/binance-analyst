"""
from app.core.settings import settings
from app.backend.binance import binance
from app.binance.account import *
from pprint import pprint as pp
import pandas as pd
from time import sleep
from app.helpers import *
from datetime import datetime
from app.analysis import *

t1 = datetime.now()
#pp(dict(settings))


#pp(binance)
#pp(binance.ping())
#pp(binance.get_prices())
#pp(binance.weight())
#pp(binance.get_account_info())

pp(Account.load().__dict__)
btc = Coin("BTC")
eth = Coin("ETH")
print()
pp([btc, eth])

print()

pp(btc.to(eth))
#pp(btc.to(eth).get_klines())
#pp(binance.get_prices())


base_pairs = PairsManager.load()
#pairs = PairsManager.filter(pairs, ["BTC", "ETH"])
pairs = PairsManager.filter(
    base_pairs,
    ["BTC", "BNB", "LTC", "BAT", "ETH"],
    exclusive=True)
pairs = PairsManager.filter(
    base_pairs,
    ["BNB"],
)
dfs = PairsManager.load_dataframes(pairs)
i = 6
cdf = filter_dataframes(dfs)
cdf = trim_dataframes(cdf)
cdf = drop_missing_data_columns(cdf, perc=91)
close = filter_dataframes(dfs)

print(close)
print()


base_pairs = PairsManager.load()
pairs = PairsManager.filter(base_pairs, ["BNB", "BTC"], exclusive=True)
dfs = PairsManager.load_dataframes(pairs)
df = filter_dataframes(dfs)

print(RateOfReturn(df).simple())
print(MovingAverage(df, periods=4).mean())





t2 = datetime.now()
tdiff = t2 - t1
print(f"Took : {tdiff.seconds}.{tdiff.microseconds} seconds")
print()
"""
