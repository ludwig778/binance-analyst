from json import dump, load
from pathlib import Path
from shutil import rmtree


class FileAdapter:
    def __init__(self, dir_path: Path):
        self.dir_path = dir_path

    def create_dir(self) -> bool:
        if not self.dir_path.exists():
            self.dir_path.mkdir(parents=True)

            return True

        return False

    def delete(self, filename: str):
        (self.dir_path / filename).unlink()

    def delete_dir(self):
        rmtree(self.dir_path)

    def exists(self, filename: str):
        return (self.dir_path / filename).exists()

    def load(self, filename: str) -> dict:
        with open(self.dir_path / filename) as fd:
            return load(fd)

    def save(self, filename: str, data: dict) -> None:
        with open(self.dir_path / filename, "w") as fd:
            dump(data, fd, indent=2)
