from copy import deepcopy
from datetime import datetime, timedelta

from analyst.crypto.models import Order

NOW = int(datetime.now().strftime("%s")) * 1000
NOW_2 = int((datetime.now() + timedelta(minutes=12)).strftime("%s")) * 1000
NOW_3 = int((datetime.now() + timedelta(minutes=24)).strftime("%s")) * 1000

ORDER_1 = Order(
    id=1,
    symbol="ETHBTC",
    status="NEW",
    type="MARKET",
    side="BUY",
    price=23.4,
    stop_price=23.5,
    time_in_force="GTC",
    requested_quantity=1.0,
    executed_quantity=0.0,
    created_at=NOW,
    updated_at=NOW,
)
ORDER_2 = Order(
    id=2,
    symbol="ETHBTC",
    status="NEW",
    type="LIMIT_MAKER",
    side="SELL",
    price=23.4,
    stop_price=23.5,
    time_in_force="GTC",
    requested_quantity=2.0,
    executed_quantity=1.0,
    created_at=NOW_2,
    updated_at=NOW_2,
)
ORDER_3 = Order(
    id=3,
    symbol="ETHBTC",
    status="NEW",
    type="MARKET",
    side="BUY",
    price=23.4,
    stop_price=23.5,
    time_in_force="GTC",
    requested_quantity=2.0,
    executed_quantity=0.0,
    created_at=NOW_3,
    updated_at=NOW_3,
)
ORDER_1_UPDATED = deepcopy(ORDER_1)
ORDER_1_UPDATED.status = "CANCELLED"
ORDER_1_UPDATED.updated_at = NOW_2
