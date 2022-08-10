from pathlib import Path

from analyst.settings import get_settings


def test_settings_default_test_values():
    assert get_settings().dict() == {
        "binance_settings": {
            "api_key": "api_key",
            "api_url": "https://api.binance.com",
            "secret_key": "secret_key",
        },
        "cache_settings": {
            "dataframe_dir": Path("tests/fixtures/dataframes"),
            "metadata_dir": Path("tests/fixtures/metadata"),
        },
        "debug": False,
        "test": True,
    }
