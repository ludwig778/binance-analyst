class BinanceError(Exception):
    pass


class WrongDatetimeRange(Exception):
    pass


class InvalidInterval(Exception):
    pass


class InvalidPairCoins(Exception):
    pass


class OrderWouldMatch(Exception):
    pass


class PriceMustBeSetOnMarketMakingOrder(Exception):
    pass
