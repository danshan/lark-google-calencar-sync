from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Self

import tomli_w
from pydantic import BaseModel, Field


def default_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base).expanduser() if base else Path.home() / ".config"


def default_app_config_dir() -> Path:
    return default_config_dir() / "lark-google-calendar-sync"


class CaldavConfig(BaseModel):
    host: str = ""
    username: str = ""
    password: str = ""
    calendar_url: str = ""
    timeout_seconds: int = Field(default=30, ge=1)
    state_path: Path | None = None


class GoogleConfig(BaseModel):
    calendar_id: str = "primary"
    credentials_path: Path = Path("google.credentials.json")
    token_path: Path = Path("google.token.json")


class SyncConfig(BaseModel):
    past_days: int = Field(default=7, ge=0)
    future_days: int = Field(default=30, ge=1)
    dry_run: bool = False


class AppConfig(BaseModel):
    caldav: CaldavConfig = Field(default_factory=CaldavConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    log_path: Path = Path("lark-google-calendar-sync.log")

    @classmethod
    def default_path(cls) -> Path:
        return default_app_config_dir() / "config.toml"

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        config_path = path or cls.default_path()
        with config_path.open("rb") as file:
            data = tomllib.load(file)
        return cls.model_validate(data)

    def save(self, path: Path | None = None) -> None:
        config_path = path or self.default_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_data = self.model_dump(mode="json", exclude_none=True)
        config_path.write_text(tomli_w.dumps(config_data), encoding="utf-8")
