from datetime import datetime, timedelta
from os import environ
from pprint import pprint as pp

import numpy as np
import pandas as pd

from analyst.adapters import get_adapters
from analyst.adapters.local_file import LocalFileAdapter
from analyst.controllers.binance import *
from analyst.settings import get_settings

environ["ANALYST_REDIS_HOST"] = ""
environ["ANALYST_CACHE_DIR"] = "tests/fixture_data"

s = get_settings()
a = get_adapters(settings=s)

if isinstance(a.cache, LocalFileAdapter) and not a.cache.dir_path.exists():
    print("Create default local file cache directory")
    a.cache.create_dir()

acc = load_account(a)
pa = load_exchange_data(a)
