import json

import pytest

from tasks_reminder.auth import AuthError, extract_code
from tasks_reminder.settings import Settings, SettingsStore, parse_notify_times


def test_parse_notify_times_normalizes_and_sorts():
    assert parse_notify_times("17:00, 8:00、08:00") == ["08:00", "17:00"]


@pytest.mark.parametrize("text", ["", "25:00", "8:60", "8時", "08-00"])
def test_parse_notify_times_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_notify_times(text)


def test_schedule_times_use_jst():
    times = Settings(notify_times=["08:00", "17:30"]).schedule_times()
    assert [(t.hour, t.minute) for t in times] == [(8, 0), (17, 30)]
    assert all(str(t.tzinfo) == "Asia/Tokyo" for t in times)


def test_settings_store_defaults_and_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    assert store.settings.notify_times == ["08:00", "17:00"]
    assert store.settings.tasklist_ids == []

    store.settings.tasklist_ids = ["abc"]
    store.settings.notify_times = ["07:30"]
    store.save()

    assert json.loads(path.read_text()) == {"notify_times": ["07:30"], "tasklist_ids": ["abc"]}
    reloaded = SettingsStore(path)
    assert reloaded.settings == store.settings


def test_extract_code_from_url_and_raw():
    url = "http://localhost/?state=xyz&code=4/0AbC-def&scope=https://www.googleapis.com/auth/tasks.readonly"
    assert extract_code(url) == "4/0AbC-def"
    assert extract_code("  4/0raw  ") == "4/0raw"


@pytest.mark.parametrize("text", ["", "http://localhost/?error=access_denied", "http://localhost/?state=x"])
def test_extract_code_errors(text):
    with pytest.raises(AuthError):
        extract_code(text)
