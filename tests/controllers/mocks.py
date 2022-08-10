def mock_account_info(adapters, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_account_info",
        lambda _: adapters.cache.read("account_info"),
    )


def mock_exchange_data_info(adapters, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_exchange_info",
        lambda _: adapters.cache.read("exchange_info"),
    )


def mock_pair_prices_info(adapters, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_prices",
        lambda _: adapters.cache.read("pairs_prices"),
    )
