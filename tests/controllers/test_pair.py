from datetime import datetime

from tests.utils import equal_dataframes


def test_pair_repository_load_with_cache(controllers):
    retrieved_pairs = controllers.pair.load()

    assert len(retrieved_pairs) == 73


def test_pair_repository_load_without_cache(controllers, pairs, monkeypatch):
    monkeypatch.setattr("binance_analyst.adapters.DirectoryAdapter.file_exists", lambda *_: False)
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_exchange_info",
        lambda _: [
            {
                "symbol": symbol,
                "baseAsset": pair.base.name,
                "quoteAsset": pair.quote.name,
            }
            for symbol, pair in pairs.items()
        ],
    )
    retrieved_pairs = controllers.pair.load()

    assert len(retrieved_pairs) == 73

    assert retrieved_pairs == pairs


def test_pair_repository_filter(pairs, controllers):
    pair_repo = controllers.pair

    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH", "BNB", "USDT", "BUSD"])) == 73
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH"])) == 36
    assert len(pair_repo.filter(pairs, coin_strs=["BTC"])) == 20
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH"], exclusive=True)) == 1
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "FAKECOIN"], exclusive=True)) == 0


def test_pair_repository_load_dataframes(controllers, pairs):
    dataframes = controllers.pair.load_dataframes(
        pairs,
        interval="1d",
        start_datetime=datetime(2017, 1, 1),
        end_datetime=datetime(2022, 1, 1),
    )

    assert len(dataframes) == 73

    def get_datetime_range(df):
        return (
            df.index[0].to_pydatetime(),
            df.index[-1].to_pydatetime(),
        )

    assert get_datetime_range(dataframes["BNBBTC"]) == (
        datetime(2017, 7, 15),
        datetime(2022, 1, 1),
    )
    assert get_datetime_range(dataframes["LINKUSDT"]) == (
        datetime(2019, 1, 17),
        datetime(2022, 1, 1),
    )
    assert get_datetime_range(dataframes["LUNABTC"]) == (
        datetime(2020, 8, 20),
        datetime(2022, 1, 1),
    )

    assert dataframes["XTZETH"].empty


def test_pair_repository_get_klines(controllers, pairs, adapters, dataframes_1d, monkeypatch):
    def mock_get_historical_klines(*_args, **_kwargs):
        return adapters.metadata.read_json("BNBBTC_1d_first_week_of_2021.json")

    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_historical_klines", mock_get_historical_klines
    )

    dataframe = controllers.pair.get_klines(
        pairs["BNBBTC"],
        interval="1d",
        start_datetime=datetime(2021, 1, 1),
        end_datetime=datetime(2021, 1, 7),
    )

    assert equal_dataframes(dataframe, dataframes_1d["BNBBTC"]["2021-01-01":"2021-01-07"])


def test_pair_repository_get_klines_full(controllers, pairs, adapters, dataframes_1d, monkeypatch):
    def mock_get_historical_klines(*_args, start_datetime=None, end_datetime=None, **_kwargs):
        if (start_datetime, end_datetime) == (datetime(2020, 12, 25), datetime(2021, 1, 1)):
            return adapters.metadata.read_json("BNBBTC_1d_last_week_of_2020.json")
        if (start_datetime, end_datetime) == (datetime(2021, 1, 7), datetime(2021, 1, 14)):
            return adapters.metadata.read_json("BNBBTC_1d_second_week_of_2021.json")

    monkeypatch.setattr(
        "binance_analyst.adapters.DataFrameDirectoryAdapter.file_exists", lambda *_: True
    )
    monkeypatch.setattr(
        "binance_analyst.adapters.DataFrameDirectoryAdapter.read_dataframe",
        lambda *_: dataframes_1d["BNBBTC"]["2021-01-01":"2021-01-07"],
    )
    monkeypatch.setattr(
        "binance_analyst.adapters.BinanceAdapter.get_historical_klines", mock_get_historical_klines
    )

    dataframe = controllers.pair.get_klines(
        pairs["BNBBTC"],
        interval="1d",
        start_datetime=datetime(2020, 12, 25),
        end_datetime=datetime(2021, 1, 14),
        full=True,
    )

    assert equal_dataframes(dataframe, dataframes_1d["BNBBTC"]["2020-12-25":"2021-01-14"])
