from typing import Optional


def mock_coroutine_return(returns):
    async def wrapped_coroutine(*_args, **_kwargs):
        return returns

    return wrapped_coroutine


def mock_account_info(adapters, monkeypatch, account_data: Optional[dict] = None):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_account_info",
        mock_coroutine_return(account_data or adapters.cache.read("account_info")),
    )


def mock_exchange_data_info(adapters, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_exchange_info",
        mock_coroutine_return(adapters.cache.read("exchange_info")),
    )


def mock_pair_prices_info(adapters, monkeypatch):
    monkeypatch.setattr(
        "analyst.adapters.binance.BinanceAdapter.get_prices",
        mock_coroutine_return(adapters.cache.read("pairs_prices")),
    )
