from pytest import fixture


@fixture(scope="function")
def pairs(controllers):
    return controllers.pair.load()
