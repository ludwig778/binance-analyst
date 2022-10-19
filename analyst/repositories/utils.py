from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from bson.decimal128 import Decimal128

from analyst.bot.strategies.base import StrategyFlags, StrategyState


def serialize_account_obj(account):
    account = deepcopy(account)

    for coin_name, coin_amount in list(account.items()):
        account[coin_name] = float(coin_amount.quantity)

    return account


def serialize_order_obj(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_order_obj(v) for k, v in list(obj.items())}
    return obj


# TODO RENAME AND FACTORY IN OWN UTIL FILE, MAKE REAL RECURSIVE FUNC
def serialize_obj(obj, **kwargs):
    if isinstance(obj, Decimal):
        return Decimal128(str(obj))
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, UUID) and kwargs.get("serialize_uuid"):
        return str(obj)
    elif isinstance(obj, timedelta):
        return (datetime.min + obj).isoformat()
    elif isinstance(obj, StrategyState):
        return obj.value
    elif isinstance(obj, StrategyFlags):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: serialize_obj(v, **kwargs) for k, v in list(obj.items())}
    elif isinstance(obj, (list, set)):
        return [serialize_obj(item, **kwargs) for item in obj]

    return obj


def recover_decimal(dict_item):
    if dict_item is None:
        return None

    if isinstance(dict_item, list):
        return dict_item

    for k, v in list(dict_item.items()):
        if isinstance(v, dict):
            recover_decimal(v)
        elif isinstance(v, list):
            recover_decimal(v)
        elif isinstance(v, Decimal128):
            dict_item[k] = Decimal(str(v))

    return dict_item


def from_isoformat_to_timedelta(isoformat: str) -> timedelta:
    return datetime.fromisoformat(isoformat) - datetime.min
