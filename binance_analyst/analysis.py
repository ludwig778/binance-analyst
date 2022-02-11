import numpy as np
from pandas import DataFrame


class DataFrameHandler:
    def __init__(self, df):
        self.df = df


class RateOfReturn(DataFrameHandler):
    def simple(self) -> DataFrame:
        return self.df.pct_change(1).mean() * len(self.df)

    def compound(self):
        return (1 + self.df.pct_change(1).mean()) ** len(self.df) - 1

    def log(self):
        return np.log(self.df.pct_change(1).mean() + 1) * len(self.df)


class MovingAverage(DataFrameHandler):
    def __init__(self, *args, periods=5, **kwargs):
        super().__init__(*args, **kwargs)
        self.periods = periods

    def mean(self):
        return self.df.rolling(self.periods).mean()
