from datetime import datetime

from binance_analyst.repositories import get_repositories


def test_pair_repository_load_with_cache(repositories):
    retrieved_pairs = repositories.pair.load()

    assert len(retrieved_pairs) == 73


def test_pair_repository_load_without_cache(repositories, pairs, monkeypatch):
    monkeypatch.setattr("binance_analyst.adapters.FileAdapter.exists", lambda *_: False)
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
    retrieved_pairs = repositories.pair.load()

    assert len(retrieved_pairs) == 73

    assert retrieved_pairs == pairs


def test_pair_repository_filter(pairs):
    pair_repo = get_repositories().pair

    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH", "BNB", "USDT", "BUSD"])) == 73
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH"])) == 36
    assert len(pair_repo.filter(pairs, coin_strs=["BTC"])) == 20
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "ETH"], exclusive=True)) == 1
    assert len(pair_repo.filter(pairs, coin_strs=["BTC", "FAKECOIN"], exclusive=True)) == 0


def test_pair_repository_load_dataframes(repositories, pairs):
    dataframes = repositories.pair.load_dataframes(
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
