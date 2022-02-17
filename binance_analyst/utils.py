from pandas import DataFrame, concat


def filter_dataframes(dfs, column="close") -> DataFrame:
    return concat([df[[column]].rename(columns={column: key}) for key, df in dfs.items()], axis=1)


def trim_dataframes(df, perc=50) -> DataFrame:
    def check_nan_values(values):
        return values.isna().sum() / len(values) * 100

    for row in df.iloc:
        if check_nan_values(row) < 50:
            break

    # TODO: REMOVE THAT
    # for rrow in df[::-1].iloc:
    #    if check_nan_values(rrow) <= 0:
    #        break

    df = df.loc[row.name :]  # noqa :rrow.name]

    return df


def drop_missing_data_columns(df, perc=90) -> DataFrame:
    return df.dropna(axis=1, thresh=len(df) / (100 / perc))
