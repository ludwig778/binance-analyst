from binance_analyst.adapters import get_adapters


def test_adapters():
    adapters = get_adapters()

    assert adapters.binance
    assert adapters.dataframe
    assert adapters.metadata
