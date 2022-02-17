from pandas.testing import assert_frame_equal


def equal_dataframes(df, other_df):
    try:
        assert_frame_equal(df, other_df)
        return True
    except Exception:
        return False
