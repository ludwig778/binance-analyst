from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from binance_analyst.adapters import get_adapters
from binance_analyst.core.settings import get_settings
from binance_analyst.repositories import get_repositories

s = get_settings()
a = get_adapters()
r = get_repositories()

if not a.metadata.dir_path.exists() or not a.dataframe.dir_path.exists():
    print("Create default adapters directories")
    a.metadata.create_dir()
    a.dataframe.create_dir()

pairs = r.pair.load()
