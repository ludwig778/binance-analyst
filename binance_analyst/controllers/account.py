from binance_analyst.models import Account, Coin, CoinAmount
from binance_analyst.controllers.base import AdaptersAwareController


class AccountController(AdaptersAwareController):
    def load(self) -> Account:
        account_info = self.adapters.binance.get_account_info()

        coins = {}
        for coin in account_info.get("balances"):
            amount = float(coin.get("free", 0))

            if amount:
                name = coin.get("asset")
                coins[name] = CoinAmount(coin=Coin(name=name), amount=amount)

        return Account(coins=coins)
