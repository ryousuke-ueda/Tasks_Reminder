"""環境変数から起動設定を読み込む。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class Config:
    discord_token: str
    owner_id: int
    data_dir: Path

    @property
    def credentials_path(self) -> Path:
        return self.data_dir / "credentials.json"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token.json"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"


def load_config() -> Config:
    load_dotenv()

    token = os.environ.get("DISCORD_TOKEN", "").strip()
    owner = os.environ.get("DISCORD_OWNER_ID", "").strip()
    missing = [name for name, value in (("DISCORD_TOKEN", token), ("DISCORD_OWNER_ID", owner)) if not value]
    if missing:
        raise SystemExit(f"環境変数が設定されていません: {', '.join(missing)}（.env.example を参照）")
    if not owner.isdigit():
        raise SystemExit("DISCORD_OWNER_ID は数字のユーザー ID を指定してください")

    data_dir = Path(os.environ.get("DATA_DIR", "data")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(discord_token=token, owner_id=int(owner), data_dir=data_dir)
