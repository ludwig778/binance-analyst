from decimal import Decimal

from pandas.testing import assert_frame_equal

from analyst.crypto.models import MarketStreamTicker


def equal_dataframes(df, other_df):
    try:
        assert_frame_equal(df, other_df)
        return True
    except Exception:
        return False


def forge_stream_ticker(
    symbol, ask_price, bid_price, ask_quantity="1_000_000", bid_quantity="1_000_000", trades=500
):
    return MarketStreamTicker(
        symbol=symbol,
        last_price=Decimal(ask_price),
        ask_price=Decimal(ask_price),
        ask_quantity=Decimal(ask_quantity),
        bid_price=Decimal(bid_price),
        bid_quantity=Decimal(bid_quantity),
        trades=trades,
    )
