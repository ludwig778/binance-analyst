from binance_analyst.exceptions import InvalidPairCoins
from binance_analyst.objects import Account, Coin, CoinAmount
from binance_analyst.repositories import Repositories


def convert_account_coins_to(repositories: Repositories, account: Account, to: Coin) -> CoinAmount:
    total = CoinAmount(coin=to, amount=0.0)

    for asset in account.coins.values():
        if asset.coin == to:
            total.amount += asset.amount

        else:
            try:
                converted = repositories.exchange.convert(asset, to)
            except InvalidPairCoins:
                transitions = repositories.exchange.get_transitional_coins(asset.coin, to)

                transition_results = {}
                for transition in transitions:
                    converted = repositories.exchange.convert(
                        repositories.exchange.convert(asset, transition), to
                    )
                    transition_results[transition] = converted

                converted = sorted(transition_results.values(), key=lambda x: x.amount)[-1]

            total.amount += converted.amount

    return total
