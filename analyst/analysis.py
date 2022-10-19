from datetime import datetime

from pandas import DataFrame, IndexSlice, concat


def get_returns(df) -> DataFrame:
    return df.pct_change(1)


def remove_empty_dataframes(asset_dataframes: DataFrame) -> DataFrame:
    return {asset: dataframe for asset, dataframe in asset_dataframes.items() if not dataframe.empty}


def get_column_values(asset_dataframes: DataFrame, column_name: str) -> DataFrame:
    dataframes = []

    for pair, pair_dataframe in asset_dataframes.items():
        if pair_dataframe.empty:
            dataframes.append(DataFrame({pair: []}))
        else:
            column = pair_dataframe[[column_name]]
            column.columns = [pair]

            dataframes.append(column)

    return concat(dataframes, join="outer", axis=1)


def trim_dataframes(df: DataFrame, start: datetime, end: datetime) -> DataFrame:
    return df.loc[start:end]  # type: ignore


"""
# TODO: Keep ?
def trim_dataframes(df, perc=50) -> DataFrame:
    def check_nan_values(values):
        return values.isna().sum() / len(values) * 100

    for row in df.iloc:
        if check_nan_values(row) < perc:
            break

    # TODO: REMOVE THAT
    # for rrow in df[::-1].iloc:
    #    if check_nan_values(rrow) <= 0:
    #        break

    df = df.loc[row.name :]  # noqa :rrow.name]

    return df
"""


def drop_missing_data_columns(df: DataFrame, perc: int = 90) -> DataFrame:
    return df.dropna(axis=1, thresh=len(df) / (100 / perc))


def prefix_columns(df: DataFrame, prefix: str) -> DataFrame:
    df.columns = [prefix + column for column in df.columns]
    return df


def filter_dataframes_leveled_columns(
    df: DataFrame,
    first_level=slice(None),
    second_level=slice(None),
) -> DataFrame:
    return df.loc[:, IndexSlice[first_level, second_level]]


def swap_dataframe_levels(df):
    return df.swaplevel(axis=1).reindex(df.columns.unique(level=1), level=0, axis=1)
