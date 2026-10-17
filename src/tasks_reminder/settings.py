"""Bot との対話で変更できる設定（通知時刻・対象リスト）の保存と読み込み。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import time
from pathlib import Path

from .config import JST

DEFAULT_NOTIFY_TIMES = ["08:00", "17:00"]
MAX_NOTIFY_TIMES = 10

_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass
class Settings:
    notify_times: list[str] = field(default_factory=lambda: list(DEFAULT_NOTIFY_TIMES))
    # 空のときはすべてのタスクリストを対象にする
    tasklist_ids: list[str] = field(default_factory=list)

    def schedule_times(self) -> list[time]:
        result = []
        for text in self.notify_times:
            hour, minute = map(int, text.split(":"))
            result.append(time(hour=hour, minute=minute, tzinfo=JST))
        return result


def parse_notify_times(text: str) -> list[str]:
    """"8:00, 17:30" のような入力を検証し、"HH:MM" の昇順リストに正規化する。"""
    tokens = [t for t in re.split(r"[\s,、，]+", text.strip()) if t]
    if not tokens:
        raise ValueError("時刻を 1 つ以上指定してください（例: 08:00,17:00）")

    normalized = set()
    for token in tokens:
        match = _TIME_PATTERN.match(token)
        if not match:
            raise ValueError(f"時刻の形式が正しくありません: {token}（HH:MM で指定してください）")
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError(f"存在しない時刻です: {token}")
        normalized.add(f"{hour:02d}:{minute:02d}")

    if len(normalized) > MAX_NOTIFY_TIMES:
        raise ValueError(f"通知時刻は最大 {MAX_NOTIFY_TIMES} 個までです")
    return sorted(normalized)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.settings = self._load()

    def _load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        defaults = Settings()
        times = raw.get("notify_times") or defaults.notify_times
        return Settings(
            notify_times=parse_notify_times(",".join(times)),
            tasklist_ids=[str(i) for i in raw.get("tasklist_ids", [])],
        )

    def save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.settings), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
