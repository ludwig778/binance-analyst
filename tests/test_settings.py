from binance_analyst.core.settings import get_settings


def test_settings():
    settings = get_settings()

    assert settings.binance_settings
    assert settings.cache_settings
