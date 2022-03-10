from binance_analyst.exceptions import InvalidPairCoins
from binance_analyst.models import Account, Coin, CoinAmount
from binance_analyst.controllers import Controllers


def convert_account_coins_to(controllers: Controllers, account: Account, to: Coin) -> CoinAmount:
    total = CoinAmount(coin=to, amount=0.0)

    for asset in account.coins.values():
        if asset.coin == to:
            total.amount += asset.amount

        else:
            try:
                converted = controllers.exchange.convert(asset, to)
            except InvalidPairCoins:
                transitions = controllers.exchange.get_transitional_coins(asset.coin, to)

                transition_results = {}
                for transition in transitions:
                    converted = controllers.exchange.convert(
                        controllers.exchange.convert(asset, transition), to
                    )
                    transition_results[transition] = converted

                converted = sorted(transition_results.values(), key=lambda x: x.amount)[-1]

            total.amount += converted.amount

    return total
