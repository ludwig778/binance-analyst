from binance_analyst.repositories import get_repositories


def test_repositories():
    repositories = get_repositories()

    assert repositories.account
    assert repositories.pair
