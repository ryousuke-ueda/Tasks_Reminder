"""タスクを期日までの日数で分類する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .google_tasks import Task


class Bucket(Enum):
    OVERDUE = "overdue"  # 期日を過ぎた（d < 0）
    WITHIN_3 = "within_3"  # 今日を含めて 0〜3 日後
    WITHIN_7 = "within_7"  # 4〜7 日後
    WITHIN_30 = "within_30"  # 8〜30 日後


def bucket_for(days_until_due: int) -> Bucket | None:
    if days_until_due < 0:
        return Bucket.OVERDUE
    if days_until_due <= 3:
        return Bucket.WITHIN_3
    if days_until_due <= 7:
        return Bucket.WITHIN_7
    if days_until_due <= 30:
        return Bucket.WITHIN_30
    return None


@dataclass
class Classified:
    buckets: dict[Bucket, list[Task]] = field(default_factory=lambda: {b: [] for b in Bucket})
    no_due_count: int = 0

    def is_empty(self) -> bool:
        return not any(self.buckets.values())


def classify(tasks: list[Task], today: date) -> Classified:
    result = Classified()
    for task in tasks:
        if task.due is None:
            result.no_due_count += 1
            continue
        bucket = bucket_for((task.due - today).days)
        if bucket is not None:
            result.buckets[bucket].append(task)

    for items in result.buckets.values():
        items.sort(key=lambda t: (t.due, t.list_title, t.title))
    return result
