from hartware_lib.adapters.directory import DirectoryAdapter
from pandas import DataFrame, read_json


class DataFrameDirectoryAdapter(DirectoryAdapter):
    def read_dataframe(self, filename: str) -> DataFrame:
        df = read_json(self.dir_path / filename)

        df["timestamp"] = df.index
        df.set_index("timestamp", inplace=True)

        return df

    def write_dataframe(self, filename: str, df: DataFrame) -> None:
        df.to_json(self.dir_path / filename, indent=2)
