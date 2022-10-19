from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from analyst.bot.strategies.base import Strategy


logger = getLogger("strategies.registry")


class RegisteredStrategy(type):
    instances: Dict[str, Strategy] = {}

    def __new__(cls, clsname, superclasses, attributedict):
        newclass = type.__new__(cls, clsname, superclasses, attributedict)

        if superclasses:
            cls.instances[f"{newclass.name}:{newclass.version}"] = newclass

            logger.info(f"registering strategy: {newclass.name}:{newclass.version}")

        return newclass

    @classmethod
    def get_class(cls, name, version):
        strategy_class = cls.instances.get(f"{name}:{version}")

        logger.info(f"get strategy: {name}:{version} {'ok' if strategy_class else 'not found'}")

        return strategy_class
