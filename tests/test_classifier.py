from datetime import date, timedelta

import pytest

from tasks_reminder.classifier import Bucket, bucket_for, classify
from tasks_reminder.google_tasks import Task, parse_due

TODAY = date(2026, 10, 16)


def make_task(title: str, days: int | None, list_title: str = "マイタスク") -> Task:
    due = None if days is None else TODAY + timedelta(days=days)
    return Task(id=title, title=title, list_title=list_title, due=due)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-10, Bucket.OVERDUE),
        (-1, Bucket.OVERDUE),
        (0, Bucket.WITHIN_3),
        (3, Bucket.WITHIN_3),
        (4, Bucket.WITHIN_7),
        (7, Bucket.WITHIN_7),
        (8, Bucket.WITHIN_30),
        (30, Bucket.WITHIN_30),
        (31, None),
    ],
)
def test_bucket_boundaries(days, expected):
    assert bucket_for(days) == expected


def test_classify_groups_sorts_and_counts_no_due():
    tasks = [
        make_task("c", 2),
        make_task("a", 0),
        make_task("old", -3),
        make_task("week", 5),
        make_task("month", 20),
        make_task("far", 45),
        make_task("nodue1", None),
        make_task("nodue2", None),
    ]
    result = classify(tasks, TODAY)

    assert [t.title for t in result.buckets[Bucket.OVERDUE]] == ["old"]
    assert [t.title for t in result.buckets[Bucket.WITHIN_3]] == ["a", "c"]
    assert [t.title for t in result.buckets[Bucket.WITHIN_7]] == ["week"]
    assert [t.title for t in result.buckets[Bucket.WITHIN_30]] == ["month"]
    assert result.no_due_count == 2
    assert not result.is_empty()


def test_classify_across_month_boundary():
    today = date(2026, 1, 30)
    task = Task(id="x", title="x", list_title="l", due=date(2026, 2, 2))  # 3 日後
    assert classify([task], today).buckets[Bucket.WITHIN_3] == [task]


def test_classify_empty():
    result = classify([make_task("far", 31), make_task("nodue", None)], TODAY)
    assert result.is_empty()
    assert result.no_due_count == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-20T00:00:00.000Z", date(2026, 10, 20)),
        ("2026-10-20", date(2026, 10, 20)),
        (None, None),
        ("", None),
    ],
)
def test_parse_due(raw, expected):
    assert parse_due(raw) == expected
