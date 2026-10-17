# tasks_reminder

Google Tasks の未完了タスクを、毎朝 8:00 / 毎夕 17:00（日本時間）に Discord の DM でリマインドする Bot です。

| 区分 | 条件 |
|---|---|
| ⚠️ 期限切れ | 期日を過ぎたもの |
| 🔴 3日以内 | 今日〜3日後 |
| 🟡 1週間以内 | 4〜7日後 |
| 🟢 1ヶ月以内 | 8〜30日後 |
| 📝 期日なし | 件数のみ表示 |

各タスクはクリックすると Google Tasks で開けます。

## DM で使えるコマンド

| コマンド | 内容 |
|---|---|
| `/google_auth` | Google アカウントを連携（トークン失効時の再連携も同じ） |
| `/lists` | 通知対象のタスクリストを選ぶ（初期値: すべて） |
| `/times 08:00,17:00` | 通知時刻を変更（日本時間・複数可） |
| `/settings` | 現在の設定と次回通知時刻を表示 |
| `/remind_now` | 今すぐリマインドを表示 |

コマンドは `.env` の `DISCORD_OWNER_ID` のユーザーだけが使えます。

---

## セットアップ

### 1. Google Cloud の準備（初回のみ）

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成する
2. 「API とサービス」→「ライブラリ」で **Google Tasks API** を有効にする
3. 「Google Auth Platform」で OAuth 同意画面を設定する
   - 対象（Audience）: **外部（External）**。テストユーザーに自分の Gmail を追加する
   - **公開ステータスを「本番環境（In production）」にする**
     （「テスト」のままだと、トークンが **7日で失効** します。個人利用なら Google の審査は不要で、
     認可時に「確認されていないアプリ」の警告が出るだけです）
4. 「クライアント」で **アプリケーションの種類: デスクトップアプリ** のクライアントを作成し、JSON をダウンロードする

### 2. Discord Bot の準備（初回のみ）

1. [Discord Developer Portal](https://discord.com/developers/applications) で New Application を作成する
2. **Bot** タブで「Reset Token」からトークンを取得する（特権 Intent は不要）
3. **Installation** タブで **Guild Install** を有効にし、Install Link（Discord Provided Link）から
   **自分専用の Discord サーバー**（新しく作ったもので OK）に Bot を招待する
   - Bot が DM を送ったり、DM でコマンドを使ったりするには **Bot との共通サーバーが必要** です
   - そのサーバーのプライバシー設定で「ダイレクトメッセージを許可する」を ON にしておく
4. 自分のユーザー ID を控える（Discord の設定 → 詳細設定 → 開発者モード ON → 自分のアイコンを右クリック →「ユーザー ID をコピー」）

> Bot は起動するたびに「起動しました」という DM を送ります。これで DM 一覧に Bot が現れ、
> Google の連携状態と次回の通知時刻も確認できます。DM が届かない場合はログ（`journalctl -u tasks-reminder`）に原因が出ます。

### 3. Ubuntu Server へのインストール

```bash
sudo apt install -y python3 python3-venv git
cd ~ && git clone <このリポジトリ> tasks_reminder   # または scp などでコピー
cd tasks_reminder
python3 -m venv .venv
.venv/bin/pip install -e .

cp .env.example .env
nano .env   # DISCORD_TOKEN と DISCORD_OWNER_ID を記入
chmod 600 .env

mkdir -p data
# 手元の PC から、ダウンロードした OAuth クライアントの JSON を転送
#   scp client_secret_xxx.json <server>:~/tasks_reminder/data/credentials.json
chmod 600 data/credentials.json
```

### 4. 常駐化（systemd）

```bash
sudo cp deploy/tasks-reminder.service /etc/systemd/system/
sudo nano /etc/systemd/system/tasks-reminder.service   # YOUR_USER を書き換え
sudo systemctl daemon-reload
sudo systemctl enable --now tasks-reminder
journalctl -u tasks-reminder -f   # ログ確認
```

サーバーのタイムゾーンが何であっても、通知時刻は日本時間で動作します。

### 5. Discord で連携

起動すると Bot から「起動しました」の DM が届くので、その DM で次の順に実行します。

1. `/google_auth` → リンクを開いて許可 → `http://localhost/?...`（「接続できません」と表示されるが正常）の
   アドレスバーの URL をコピー → 「URL を貼り付ける」ボタンから貼り付け
2. `/lists` で通知したいリストを選択（全部でよければ不要）
3. `/remind_now` で表示を確認

---

## 開発

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

| ファイル | 役割 |
|---|---|
| `src/tasks_reminder/bot.py` | Bot 本体・定期実行・リマインド組み立て |
| `src/tasks_reminder/commands.py` | スラッシュコマンドとボタン・メニュー |
| `src/tasks_reminder/auth.py` | Google OAuth（Discord 経由の認可フロー） |
| `src/tasks_reminder/google_tasks.py` | Google Tasks API ラッパー |
| `src/tasks_reminder/classifier.py` | 期日による分類 |
| `src/tasks_reminder/formatter.py` | Discord 表示の整形（文字数上限の処理含む） |
| `src/tasks_reminder/settings.py` | 対話で変更する設定の保存（`data/settings.json`） |

### 仕様メモ

- Google Tasks API の期日（`due`）は **日付のみ**（時刻は取得できない）ため、日付単位で分類しています。
- 権限は読み取り専用（`tasks.readonly`）です。
- Bot が停止していた時間帯の通知は、再起動後にまとめて送られません（`/remind_now` で確認できます）。
- 調査メモ: [docs/google_tasks_api.md](docs/google_tasks_api.md)
