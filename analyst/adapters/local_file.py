from logging import getLogger

from hartware_lib.adapters.directory import DirectoryAdapter
from pandas import DataFrame, read_json, to_datetime

logger = getLogger(__name__)


class LocalFileAdapter(DirectoryAdapter):
    def _format_filename(self, name: str) -> str:
        return f"{name}.json"

    def exists(self, name: str) -> bool:
        return self.file_exists(self._format_filename(name))

    def delete(self, name: str) -> None:
        return self.delete_file(self._format_filename(name))

    def read(self, name: str) -> dict:
        return self.read_json_file(self._format_filename(name))

    def save(self, name: str, data: dict) -> None:
        self.save_json_file(self._format_filename(name), data)

    def read_dataframe(self, name: str) -> DataFrame:
        data = read_json(self.read(name))

        df = DataFrame.from_dict(data)

        df["timestamp"] = to_datetime(df.index, unit="ms")
        df.set_index("timestamp", inplace=True)

        return df

    def save_dataframe(self, name: str, df: DataFrame) -> None:
        self.save(name, df.to_json())
