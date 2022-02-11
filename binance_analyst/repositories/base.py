from binance_analyst.adapters import Adapters


class AdaptersAwareRepository:
    def __init__(self, adapters: Adapters):
        self.adapters = adapters
