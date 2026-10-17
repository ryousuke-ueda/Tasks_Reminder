from datetime import date, datetime, timedelta

from tasks_reminder.classifier import classify
from tasks_reminder.config import JST
from tasks_reminder.formatter import (
    DESCRIPTION_LIMIT,
    MESSAGE_EMBED_TOTAL_LIMIT,
    build_greeting,
    build_reminder_messages,
    fit_lines,
    format_task_line,
    relative_label,
)
from tasks_reminder.google_tasks import Task

TODAY = date(2026, 10, 16)  # 金曜日
NOW = datetime(2026, 10, 16, 8, 0, tzinfo=JST)


def make_task(title: str, days: int | None, **kwargs) -> Task:
    due = None if days is None else TODAY + timedelta(days=days)
    return Task(id=title, title=title, list_title=kwargs.pop("list_title", "マイタスク"), due=due, **kwargs)


def test_relative_label():
    assert relative_label(-2) == "2日超過"
    assert relative_label(0) == "今日"
    assert relative_label(1) == "明日"
    assert relative_label(5) == "あと5日"


def test_format_task_line_with_link_parent_and_list():
    task = make_task(
        "レポート[最終版]",
        2,
        web_link="https://tasks.google.com/task/abc",
        parent_title="卒論",
        list_title="大学",
    )
    line = format_task_line(task, TODAY, show_list_name=True)
    assert line == "・**10/18(日)** [レポート［最終版］](https://tasks.google.com/task/abc)（あと2日） ↳ 卒論 ― 大学"


def test_format_task_line_escapes_markdown_and_untitled():
    line = format_task_line(make_task("*重要*", 0), TODAY, show_list_name=False)
    assert line == "・**10/16(金)** \\*重要\\*（今日）"
    assert "(無題)" in format_task_line(make_task("  ", 0), TODAY, show_list_name=False)


def test_fit_lines_truncates_with_remaining_count():
    lines = [f"line{i:03d}" + "x" * 90 for i in range(100)]  # 各 97 文字
    text = fit_lines(lines, limit=1000)
    assert len(text) <= 1000
    kept = text.split("\n")
    assert kept[-1] == f"…ほか{100 - (len(kept) - 1)}件"


def test_fit_lines_keeps_all_when_fits():
    assert fit_lines(["a", "b"], limit=10) == "a\nb"


def test_build_greeting_connected():
    text = build_greeting(["08:00", "17:00"], NOW, None)
    assert "起動しました" in text
    assert "08:00, 17:00" in text
    assert f"<t:{int(NOW.timestamp())}:f>" in text
    assert "✅ 連携済み" in text


def test_build_greeting_not_connected_without_next_run():
    text = build_greeting(["08:00"], None, "Google アカウントが未連携です。")
    assert "次回の通知" not in text
    assert "⚠️ Google アカウントが未連携です。" in text
    assert "/google_auth" in text


def test_build_messages_basic():
    tasks = [make_task("old", -1), make_task("soon", 1), make_task("week", 6), make_task("nodue", None)]
    messages = build_reminder_messages(classify(tasks, TODAY), TODAY, NOW, show_list_name=False)

    assert len(messages) == 1
    message = messages[0]
    assert "10/16(金) 08:00 のタスクリマインド" in message.content
    assert "期日なしのタスク: 1件" in message.content
    assert [e.title for e in message.embeds] == ["⚠️ 期限切れ（1件）", "🔴 3日以内（1件）", "🟡 1週間以内（1件）"]


def test_build_messages_empty():
    messages = build_reminder_messages(classify([], TODAY), TODAY, NOW, show_list_name=False)
    assert len(messages) == 1
    assert "ありません" in messages[0].content
    assert messages[0].embeds == []


def test_build_messages_respects_discord_limits():
    long_title = "とても長いタスク名" * 20
    tasks = [make_task(f"{long_title}{i}", d, web_link="https://tasks.google.com/task/" + "z" * 40)
             for d in (-5, 1, 5, 20) for i in range(60)]
    messages = build_reminder_messages(classify(tasks, TODAY), TODAY, NOW, show_list_name=True)

    embeds = [e for m in messages for e in m.embeds]
    assert len(embeds) == 4
    assert len(messages) > 1  # 6000 文字制限で分割される
    for m in messages:
        assert sum(len(e) for e in m.embeds) <= MESSAGE_EMBED_TOTAL_LIMIT
        assert all(len(e.description) <= DESCRIPTION_LIMIT for e in m.embeds)
    assert messages[0].content is not None
    assert all(m.content is None for m in messages[1:])
