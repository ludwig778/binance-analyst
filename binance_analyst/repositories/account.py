from binance_analyst.objects import Account, Coin, CoinAmount
from binance_analyst.repositories.base import AdaptersAwareRepository


class AccountRepository(AdaptersAwareRepository):
    def load(self) -> Account:
        account_info = self.adapters.binance.get_account_info()

        coins = {}
        for coin in account_info.get("balances"):
            amount = float(coin.get("free", 0))

            if amount:
                name = coin.get("asset")
                coins[name] = CoinAmount(Coin(name), amount)

        return Account(coins=coins)
