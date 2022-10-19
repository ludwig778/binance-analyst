import asyncio
from os import environ

from analyst.adapters.factory import get_adapters
from analyst.adapters.local_file import LocalFileAdapter
from analyst.settings import get_settings

environ["ANALYST_REDIS_HOST"] = ""
environ["ANALYST_FILE_CACHE_DIR"] = "tests/fixture_data"


async def main():
    s = get_settings()
    a = await get_adapters(settings=s)

    if isinstance(a.cache, LocalFileAdapter) and not a.cache.dir_path.exists():
        print("Create default local file cache directory")
        a.cache.create_dir()

    symbols = a.cache.read("symbols")

    account_info = {
        "balances": [
            {"asset": "BTC", "free": "1.00000000", "locked": "0.00000000"},
            {"asset": "LTC", "free": "2.00000000", "locked": "0.00000000"},
            {"asset": "ETH", "free": "3.50000000", "locked": "0.00000000"},
            {"asset": "BNB", "free": "10.00000000", "locked": "0.00000000"},
            {"asset": "DOGE", "free": "0.00000000", "locked": "0.00000000"},
        ]
    }
    a.cache.save("account_info", account_info)

    print("Account info: OK")

    exchange_info = await a.binance.get_exchange_info()
    exchange_info["symbols"] = [data for data in exchange_info["symbols"] if data["symbol"] in symbols]
    a.cache.save("exchange_info", exchange_info)

    print("Exchange info: OK")

    pairs_prices = [data for data in await a.binance.get_prices() if data["symbol"] in symbols]
    a.cache.save("pairs_prices", pairs_prices)

    print("Pair prices: OK")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
