from pytest import fixture


@fixture(scope="function")
def pairs(repositories):
    return repositories.pair.load()
