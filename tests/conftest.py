from pytest import fixture

from binance_analyst.adapters import get_adapters


@fixture(scope="function", autouse=True)
def adapters():
    adapters = get_adapters()

    adapters.metadata.create_dir()
    adapters.dataframe.create_dir()

    adapters.metadata.save("symbols.json", {"lmao": "test"})

    yield adapters

    adapters.metadata.delete_dir()
    adapters.dataframe.delete_dir()
