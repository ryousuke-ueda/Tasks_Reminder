"""Google Tasks API の薄いラッパー。すべて同期（ブロッキング）呼び出し。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


@dataclass(frozen=True)
class TaskList:
    id: str
    title: str


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    list_title: str
    due: date | None
    web_link: str | None = None
    parent_title: str | None = None


def parse_due(value: str | None) -> date | None:
    # due は日付のみが意味を持ち、時刻部分は常に 00:00:00Z で返ってくる
    if not value:
        return None
    return date.fromisoformat(value[:10])


class TasksClient:
    def __init__(self, creds: Credentials) -> None:
        self._service = build("tasks", "v1", credentials=creds, cache_discovery=False)

    def list_tasklists(self) -> list[TaskList]:
        result: list[TaskList] = []
        page_token = None
        while True:
            res = (
                self._service.tasklists()
                .list(maxResults=100, pageToken=page_token, fields="nextPageToken,items(id,title)")
                .execute()
            )
            result += [TaskList(id=i["id"], title=i.get("title", "")) for i in res.get("items", [])]
            page_token = res.get("nextPageToken")
            if not page_token:
                return result

    def list_open_tasks(self, tasklist: TaskList) -> list[Task]:
        """未完了タスクをすべて返す（期日なしの件数も必要なので期日では絞り込まない）。"""
        items: list[dict] = []
        page_token = None
        while True:
            res = (
                self._service.tasks()
                .list(
                    tasklist=tasklist.id,
                    showCompleted=False,
                    maxResults=100,
                    pageToken=page_token,
                    fields="nextPageToken,items(id,title,due,parent,webViewLink)",
                )
                .execute()
            )
            items += res.get("items", [])
            page_token = res.get("nextPageToken")
            if not page_token:
                break

        titles = {i["id"]: i.get("title", "") for i in items}
        return [
            Task(
                id=i["id"],
                title=i.get("title", ""),
                list_title=tasklist.title,
                due=parse_due(i.get("due")),
                web_link=i.get("webViewLink"),
                parent_title=titles.get(i["parent"]) if i.get("parent") else None,
            )
            for i in items
        ]
