from pathlib import Path
from typing import Optional

from hartware_lib.pydantic.field_types import BooleanFromString
from pydantic import BaseSettings, Field

DEFAULT_CACHE_DIR = Path("cache_dir", "files")


class BinanceApiSettings(BaseSettings):
    api_url: str = "https://api.binance.com"
    stream_url: str = "wss://stream.binance.com:443/stream"
    api_key: str
    secret_key: str

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_BINANCE_"


class RedisCacheSettings(BaseSettings):
    host: Optional[str]
    port: int = 6379
    db: int = 0

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_REDIS_"


class MongoSettings(BaseSettings):
    username: str = ""
    password: str = ""
    database: str = ""
    host: str = ""
    port: int = 27017
    srv_mode: BooleanFromString = Field(default=False)  # type: ignore
    timeout_ms: int = 2000

    @property
    def is_valid(self):
        return all([self.username, self.password, self.database, self.host])

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_MONGODB_"


class RabbitMQSettings(BaseSettings):
    username: str = ""
    password: str = ""
    host: str = ""
    port: int = 5672

    @property
    def is_valid(self):
        return all([self.username, self.password, self.host])

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_RABBITMQ_"


class BotSettings(BaseSettings):
    server_host: str = "localhost"
    server_port: int = 8000

    # client_host: str = "app"
    client_host: str = "app"
    client_port: int = 8000

    jwt_algorithm: str = "HS256"
    jwt_expire_delta_seconds: int = 3600

    jwt_secret: str

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_BOT_"


class AppSettings(BaseSettings):
    test: BooleanFromString = Field(default=False)  # type: ignore
    debug: BooleanFromString = Field(default=False)  # type: ignore

    file_cache_dir: Path = DEFAULT_CACHE_DIR
    redis_cache: RedisCacheSettings = Field(default_factory=RedisCacheSettings)
    binance: BinanceApiSettings = Field(default_factory=BinanceApiSettings)
    mongo: MongoSettings = Field(default_factory=MongoSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    class Config:
        case_sensitive = False
        env_prefix = "ANALYST_"


def get_settings() -> AppSettings:
    return AppSettings()
