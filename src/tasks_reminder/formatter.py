"""分類結果を Discord のメッセージ（Embed）に整形する。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import discord

from .classifier import Bucket, Classified
from .google_tasks import Task

# Discord の上限
DESCRIPTION_LIMIT = 4096
MESSAGE_EMBED_TOTAL_LIMIT = 6000
MAX_EMBEDS_PER_MESSAGE = 10

WEEKDAYS = "月火水木金土日"

BUCKET_STYLES: dict[Bucket, tuple[str, int]] = {
    Bucket.OVERDUE: ("⚠️ 期限切れ", 0x992D22),
    Bucket.WITHIN_3: ("🔴 3日以内", 0xE74C3C),
    Bucket.WITHIN_7: ("🟡 1週間以内", 0xF1C40F),
    Bucket.WITHIN_30: ("🟢 1ヶ月以内", 0x2ECC71),
}


@dataclass
class OutgoingMessage:
    content: str | None = None
    embeds: list[discord.Embed] = field(default_factory=list)


def format_date(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def relative_label(days: int) -> str:
    if days < 0:
        return f"{-days}日超過"
    if days == 0:
        return "今日"
    if days == 1:
        return "明日"
    return f"あと{days}日"


def _escape(text: str) -> str:
    # リンク記法 [text](url) を壊さないよう角括弧は全角にする
    return discord.utils.escape_markdown(text).replace("[", "［").replace("]", "］")


def format_task_line(task: Task, today: date, show_list_name: bool) -> str:
    assert task.due is not None
    title = _escape(task.title.strip() or "(無題)")
    if task.web_link:
        title = f"[{title}]({task.web_link})"

    line = f"・**{format_date(task.due)}** {title}（{relative_label((task.due - today).days)}）"
    if task.parent_title:
        line += f" ↳ {_escape(task.parent_title)}"
    if show_list_name:
        line += f" ― {_escape(task.list_title)}"
    return line


def fit_lines(lines: list[str], limit: int = DESCRIPTION_LIMIT) -> str:
    """上限文字数に収まるだけ行を入れ、溢れた分は「…ほか N 件」にまとめる。"""
    kept: list[str] = []
    total = 0
    for index, line in enumerate(lines):
        remaining = len(lines) - index - 1
        # この行を入れた後も、残りがあれば省略表記を付けられる余裕を確保する
        reserve = len(f"\n…ほか{remaining}件") if remaining else 0
        added = len(line) + (1 if kept else 0)
        if total + added + reserve > limit:
            kept.append(f"…ほか{len(lines) - index}件")
            break
        kept.append(line)
        total += added
    return "\n".join(kept)


def build_reminder_messages(
    classified: Classified,
    today: date,
    now: datetime,
    show_list_name: bool,
) -> list[OutgoingMessage]:
    header = [f"📋 **{format_date(now.date())} {now:%H:%M} のタスクリマインド**"]
    if classified.is_empty():
        header.append("1ヶ月以内に期日のある未完了タスクはありません 🎉")
    if classified.no_due_count:
        header.append(f"📝 期日なしのタスク: {classified.no_due_count}件")

    embeds = []
    for bucket, (label, color) in BUCKET_STYLES.items():
        tasks = classified.buckets[bucket]
        if not tasks:
            continue
        lines = [format_task_line(t, today, show_list_name) for t in tasks]
        embeds.append(
            discord.Embed(title=f"{label}（{len(tasks)}件）", description=fit_lines(lines), color=color)
        )

    messages = [OutgoingMessage(content="\n".join(header))]
    for embed in embeds:
        current = messages[-1]
        current_total = sum(len(e) for e in current.embeds)
        if len(current.embeds) >= MAX_EMBEDS_PER_MESSAGE or current_total + len(embed) > MESSAGE_EMBED_TOTAL_LIMIT:
            current = OutgoingMessage()
            messages.append(current)
        current.embeds.append(embed)
    return messages
