"""DM で使うスラッシュコマンドと、その UI（ボタン・選択メニュー・入力フォーム）。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .auth import AuthError
from .google_tasks import TaskList
from .settings import parse_notify_times

if TYPE_CHECKING:
    from .bot import ReminderBot

MAX_SELECT_OPTIONS = 25


def _list_names(lists: list[TaskList]) -> str:
    return "、".join(tl.title or "(無題)" for tl in lists)


def _current_target_text(bot: ReminderBot, lists: list[TaskList]) -> str:
    if not bot.store.settings.tasklist_ids:
        return "すべてのリスト"
    return _list_names(bot.selected_tasklists(lists))


# ---- /google_auth ----


class AuthCodeModal(discord.ui.Modal, title="Google 連携：リダイレクト先 URL の入力"):
    response_url: discord.ui.TextInput = discord.ui.TextInput(
        label="ブラウザのアドレスバーの URL",
        style=discord.TextStyle.paragraph,
        placeholder="http://localhost/?state=...&code=...&scope=...",
        max_length=4000,
    )

    def __init__(self, bot: ReminderBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await asyncio.to_thread(self.bot.auth.finish_authorization, self.response_url.value)
            lists = await asyncio.to_thread(self.bot.fetch_tasklists)
        except AuthError as e:
            await interaction.followup.send(f"⚠️ {e}")
            return
        await interaction.followup.send(
            f"✅ Google アカウントを連携しました。タスクリスト {len(lists)} 件（{_list_names(lists)}）を確認しました。\n"
            "`/lists` で通知対象のリストを選べます（未設定ならすべてのリストが対象です）。"
        )


class AuthCodeView(discord.ui.View):
    def __init__(self, bot: ReminderBot) -> None:
        super().__init__(timeout=900)
        self.bot = bot

    @discord.ui.button(label="URL を貼り付ける", style=discord.ButtonStyle.primary, emoji="🔑")
    async def paste(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AuthCodeModal(self.bot))


# ---- /lists ----


class TaskListSelect(discord.ui.Select):
    def __init__(self, bot: ReminderBot, lists: list[TaskList]) -> None:
        self.bot = bot
        self.lists = lists[:MAX_SELECT_OPTIONS]
        selected = set(bot.store.settings.tasklist_ids)
        options = [
            discord.SelectOption(label=(tl.title or "(無題)")[:100], value=tl.id, default=tl.id in selected)
            for tl in self.lists
        ]
        super().__init__(
            placeholder="通知対象のリストを選択（複数可）",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        chosen = [tl for tl in self.lists if tl.id in self.values]
        settings = self.bot.store.settings
        # 全リストを選んだ場合は「すべて」扱いにして、今後追加したリストも対象にする
        settings.tasklist_ids = [] if len(chosen) == len(self.view.all_lists) else [tl.id for tl in chosen]
        self.bot.store.save()
        target = "すべてのリスト" if not settings.tasklist_ids else _list_names(chosen)
        await interaction.response.edit_message(content=f"✅ 通知対象を **{target}** に設定しました。", view=None)


class TaskListView(discord.ui.View):
    def __init__(self, bot: ReminderBot, lists: list[TaskList]) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.all_lists = lists
        self.add_item(TaskListSelect(bot, lists))

    @discord.ui.button(label="すべてのリストを対象にする", style=discord.ButtonStyle.secondary, row=1)
    async def select_all(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.bot.store.settings.tasklist_ids = []
        self.bot.store.save()
        await interaction.response.edit_message(content="✅ 通知対象を **すべてのリスト** に設定しました。", view=None)


# ---- 登録 ----


def register_commands(bot: ReminderBot) -> None:
    tree = bot.tree

    @tree.command(name="google_auth", description="Google アカウントを連携（再連携）します")
    async def google_auth(interaction: discord.Interaction) -> None:
        try:
            url = bot.auth.start_authorization()
        except AuthError as e:
            await interaction.response.send_message(
                f"⚠️ {e}\nGoogle Cloud Console で作成した **デスクトップアプリ** 用 OAuth クライアントの JSON を、"
                "サーバーの上記パスに配置してから再実行してください。"
            )
            return

        embed = discord.Embed(
            title="🔗 Google アカウント連携",
            color=discord.Color.blurple(),
            description=(
                f"1. **[こちらのリンク]({url})** を開き、通知したい Google アカウントでログインして許可してください。\n"
                "　※「Google はこのアプリを確認していません」と出た場合は「詳細」→「〜（安全ではないページ）に移動」で進めます。\n"
                "2. 許可すると `http://localhost/?...` に移動し、**「接続できません」と表示されます（これで正常です）**。\n"
                "3. そのページの **アドレスバーの URL を丸ごとコピー** し、下のボタンから貼り付けてください。\n\n"
                "このリンクは、Bot が再起動するか次に `/google_auth` を実行するまで有効です。"
            ),
        )
        await interaction.response.send_message(embed=embed, view=AuthCodeView(bot))

    @tree.command(name="lists", description="通知の対象にするタスクリストを選びます")
    async def lists_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            lists = await asyncio.to_thread(bot.fetch_tasklists)
        except AuthError as e:
            await interaction.followup.send(f"⚠️ {e}\n先に `/google_auth` で連携してください。")
            return
        if not lists:
            await interaction.followup.send("タスクリストが見つかりませんでした。")
            return

        content = f"現在の通知対象: **{_current_target_text(bot, lists)}**\n下のメニューから選び直せます。"
        if len(lists) > MAX_SELECT_OPTIONS:
            content += f"\n（メニューには先頭の {MAX_SELECT_OPTIONS} 件のみ表示しています）"
        await interaction.followup.send(content, view=TaskListView(bot, lists))

    @tree.command(name="times", description="通知時刻を変更します（日本時間）")
    @app_commands.describe(times="HH:MM をカンマ区切りで指定（例: 08:00,17:00）")
    async def times_command(interaction: discord.Interaction, times: str) -> None:
        try:
            parsed = parse_notify_times(times)
        except ValueError as e:
            await interaction.response.send_message(f"⚠️ {e}")
            return
        bot.store.settings.notify_times = parsed
        bot.store.save()
        bot.reschedule()
        await interaction.response.send_message(f"✅ 通知時刻を **{', '.join(parsed)}** に変更しました。")

    @tree.command(name="settings", description="現在の設定を表示します")
    async def settings_command(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            lists = await asyncio.to_thread(bot.fetch_tasklists)
            google_status = "✅ 連携済み"
            target = _current_target_text(bot, lists)
        except AuthError as e:
            google_status = f"⚠️ {e}"
            target = "すべてのリスト" if not bot.store.settings.tasklist_ids else "（連携後に確認できます）"

        embed = discord.Embed(title="⚙️ 現在の設定", color=discord.Color.blurple())
        embed.add_field(name="Google 連携", value=google_status, inline=False)
        embed.add_field(name="通知対象リスト", value=target, inline=False)
        embed.add_field(name="通知時刻（日本時間）", value=", ".join(bot.store.settings.notify_times), inline=False)
        next_run = bot.reminder_loop.next_iteration
        if next_run is not None:
            embed.add_field(name="次回の通知", value=discord.utils.format_dt(next_run, "R"), inline=False)
        await interaction.followup.send(embed=embed)

    @tree.command(name="remind_now", description="今すぐリマインドを表示します")
    async def remind_now(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await bot.deliver_reminder(interaction.followup.send)
