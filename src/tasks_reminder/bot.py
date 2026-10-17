"""Discord Bot 本体：定期通知とリマインド内容の組み立て。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import tasks

from .auth import AuthError, GoogleAuth
from .classifier import classify
from .config import JST, Config
from .formatter import OutgoingMessage, build_greeting, build_reminder_messages
from .google_tasks import TaskList, TasksClient
from .settings import SettingsStore

log = logging.getLogger(__name__)

# コマンドは Bot との DM でのみ使える
DM_ONLY = app_commands.AppCommandContext(guild=False, dm_channel=True, private_channel=False)
INSTALLS = app_commands.AppInstallationType(guild=True, user=True)

Sender = Callable[..., Awaitable[Any]]


class OwnerOnlyTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.client.config.owner_id:
            return True
        await interaction.response.send_message("この Bot は所有者専用です。", ephemeral=True)
        return False

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        log.exception("コマンドの実行中にエラーが発生しました", exc_info=error)
        message = "⚠️ エラーが発生しました。サーバーのログを確認してください。"
        if interaction.response.is_done():
            await interaction.followup.send(message)
        else:
            await interaction.response.send_message(message)


class ReminderBot(discord.Client):
    def __init__(self, config: Config) -> None:
        super().__init__(intents=discord.Intents.default())
        self.config = config
        self.tree = OwnerOnlyTree(self, allowed_contexts=DM_ONLY, allowed_installs=INSTALLS)
        self.store = SettingsStore(config.settings_path)
        self.auth = GoogleAuth(config.credentials_path, config.token_path)
        self.reminder_loop = tasks.loop(time=self.store.settings.schedule_times())(self._on_schedule)
        self._greeted = False

    async def setup_hook(self) -> None:
        from .commands import register_commands

        register_commands(self)
        synced = await self.tree.sync()
        log.info("スラッシュコマンドを同期しました: %s", ", ".join(c.name for c in synced))
        self.reminder_loop.start()

    async def on_ready(self) -> None:
        log.info("ログインしました: %s / 通知時刻: %s", self.user, ", ".join(self.store.settings.notify_times))
        # on_ready は再接続のたびに呼ばれるので、挨拶はプロセス起動時の 1 回だけ
        if not self._greeted:
            self._greeted = True
            await self._send_greeting()

    async def _owner(self) -> discord.User:
        return self.get_user(self.config.owner_id) or await self.fetch_user(self.config.owner_id)

    async def _send_greeting(self) -> None:
        try:
            await asyncio.to_thread(self.auth.load_credentials)
            google_error = None
        except AuthError as e:
            google_error = str(e)
        except Exception as e:
            log.exception("起動時の Google 連携確認に失敗しました")
            google_error = f"連携状態を確認できませんでした（{type(e).__name__}）"

        content = build_greeting(self.store.settings.notify_times, self.reminder_loop.next_iteration, google_error)
        try:
            owner = await self._owner()
            await owner.send(content)
            log.info("起動通知を DM で送信しました")
        except discord.Forbidden:
            log.error(
                "DM を送信できませんでした。Bot を自分のサーバーに招待して共通サーバーを作り、"
                "そのサーバーの「ダイレクトメッセージを許可する」が有効か確認してください。"
            )
        except Exception:
            log.exception("起動通知の送信に失敗しました")

    # ---- 定期通知 ----

    async def _on_schedule(self) -> None:
        # 例外が漏れるとループ自体が止まるので、ここですべて捕まえる
        try:
            owner = await self._owner()
            await self.deliver_reminder(owner.send)
        except Exception:
            log.exception("定期通知に失敗しました")

    def reschedule(self) -> None:
        self.reminder_loop.change_interval(time=self.store.settings.schedule_times())
        # 初回実行前は change_interval だけでは待機中の時刻が更新されないため再起動する
        self.reminder_loop.restart()

    async def deliver_reminder(self, send: Sender) -> None:
        try:
            messages = await asyncio.to_thread(self._collect_reminder)
        except AuthError as e:
            await send(content=f"⚠️ {e}\n`/google_auth` で Google アカウントを連携してください。")
            return
        except Exception as e:
            log.exception("タスクの取得に失敗しました")
            await send(content=f"⚠️ Google Tasks の取得に失敗しました（{type(e).__name__}）。")
            return

        for message in messages:
            await send(content=message.content, embeds=message.embeds)

    # ---- Google Tasks（同期処理。asyncio.to_thread 経由で呼ぶ） ----

    def fetch_tasklists(self) -> list[TaskList]:
        return TasksClient(self.auth.load_credentials()).list_tasklists()

    def selected_tasklists(self, lists: list[TaskList]) -> list[TaskList]:
        ids = self.store.settings.tasklist_ids
        if not ids:
            return lists
        selected = [tl for tl in lists if tl.id in ids]
        if not selected:
            log.warning("選択中のタスクリストが見つからないため、すべてのリストを対象にします")
            return lists
        return selected

    def _collect_reminder(self) -> list[OutgoingMessage]:
        client = TasksClient(self.auth.load_credentials())
        lists = self.selected_tasklists(client.list_tasklists())
        all_tasks = [task for tl in lists for task in client.list_open_tasks(tl)]

        now = datetime.now(JST)
        today = now.date()
        return build_reminder_messages(classify(all_tasks, today), today, now, show_list_name=len(lists) > 1)
