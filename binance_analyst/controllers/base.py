from binance_analyst.adapters import Adapters


class AdaptersAwareController:
    def __init__(self, adapters: Adapters):
        self.adapters = adapters
