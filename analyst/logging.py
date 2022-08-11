import logging
import logging.config
from logging import getLogger  # noqa # pylint: disable=unused-import

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "standard": {"format": "%(asctime)s %(module)s %(levelname)s %(funcName)s %(message)s"}
        },
        "handlers": {
            "default": {
                "level": logging.INFO,
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "": {"handlers": ["default"], "level": logging.DEBUG, "propagate": False},
            "requests": {"level": logging.CRITICAL},
        },
    }
)
