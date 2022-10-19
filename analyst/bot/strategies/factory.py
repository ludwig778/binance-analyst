from analyst.bot.strategies.registry import RegisteredStrategy


def get_strategy(*args, **kwargs):
    return RegisteredStrategy.get_class(*args, **kwargs)
