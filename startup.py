from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from binance_analyst.adapters import get_adapters
from binance_analyst.core.settings import get_settings
from binance_analyst.repositories import get_repositories

s = get_settings()
a = get_adapters()
r = get_repositories()

pairs = r.pair.load()
