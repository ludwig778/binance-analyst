from json import dumps, loads

from pandas import DataFrame, read_json, to_datetime
from redis import StrictRedis


class RedisAdapter:
    def __init__(self, *args, **kwargs):
        self.session = StrictRedis(*args, **kwargs)

    @property
    def connected(self) -> bool:
        return self.session.ping()

    def exists(self, name: str) -> bool:
        return self.session.exists(name) != 0

    def list(self, pattern: str = "*"):
        return self.session.keys(pattern)

    def delete(self, name: str) -> None:
        self.session.delete(name)

    def read(self, name: str) -> dict:
        return loads(self.session.get(name))

    def save(self, name: str, data: dict) -> None:
        self.session.set(name, dumps(data))

    def read_dataframe(self, name: str) -> DataFrame:
        data = read_json(self.read(name))

        df = DataFrame.from_dict(data)

        df["timestamp"] = to_datetime(df.index, unit="ms")
        df.set_index("timestamp", inplace=True)

        return df

    def save_dataframe(self, name: str, df: DataFrame) -> None:
        self.save(name, df.to_json())
