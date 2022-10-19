import logging
import logging.config

from analyst.settings import get_settings

settings = get_settings()


logging.config.dictConfig(
    {
        "version": 1,
        # "disable_existing_loggers": True,
        "formatters": {
            "standard": {"format": "%(asctime)s %(levelname)-8s %(name)-19s %(message)s"},
            "raw": {"format": "%(asctime)s %(levelname)-8s %(name)-19s %(message)s"},
            # "raw": {"format": "%(message)s"}
        },
        "handlers": {
            "default": {
                "level": logging.DEBUG,
                "formatter": "raw",  # "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "level": logging.DEBUG,
                "formatter": "standard",
                "class": "logging.FileHandler",
                "filename": "analyst.log" if not settings.test else "analyst_test.log",
                "mode": "a",
            },
            "null": {
                "class": "logging.NullHandler",
            },
        },
        "loggers": {
            "": {"handlers": ["file"], "level": logging.DEBUG, "propagate": False},
            "websockets.client": {"handlers": ["file"], "level": logging.INFO, "propagate": False},
            "asyncio": {"handlers": ["file"], "level": logging.WARNING, "propagate": False},
        },
    }
)
