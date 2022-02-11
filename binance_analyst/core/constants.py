from datetime import datetime, timedelta

NO_DAY = timedelta(days=0)
DAY = timedelta(days=1)
WEEK = DAY * 7
MONTH = DAY * 30
YEAR = DAY * 365
TODAY = datetime.now().date()
