from motor.motor_asyncio import AsyncIOMotorClient

from analyst.settings import MongoSettings


class MongoAdapter:
    def __init__(self, settings: MongoSettings):
        self._client = AsyncIOMotorClient(
            "mongodb://" f"{settings.username}:{settings.password}@" f"{settings.host}:{settings.port}/",
            uuidRepresentation="standard",
        )
        self._database = self._client[settings.database]

    def get_collection(self, name: str):
        return self._database[name]
