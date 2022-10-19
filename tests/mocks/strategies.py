from analyst.bot.strategies.base import Strategy, StrategyFlags


class DummyStrategy(Strategy):
    name = "dummy"
    version = "v0"

    class Flags(StrategyFlags):
        default = ()

    @classmethod
    def create(cls, *args, **kwargs):
        return cls.post_create(*args, **kwargs)
