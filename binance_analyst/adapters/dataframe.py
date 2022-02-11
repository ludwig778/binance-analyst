from pandas import DataFrame, read_json

from binance_analyst.adapters.file import FileAdapter


class DataFrameFileAdapter(FileAdapter):
    def load(self, filename: str) -> DataFrame:
        df = read_json(self.dir_path / filename)
        df.index.rename("timestamp", inplace=True)

        return df

    def save(self, filename: str, df: DataFrame) -> None:
        df.to_json(self.dir_path / filename, indent=2)
