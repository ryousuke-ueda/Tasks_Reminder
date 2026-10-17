# Google Tasks API 調査メモ

調査日: 2026-10-16
対象: Google Tasks API v1(`tasks.googleapis.com`)

---

## 1. 概要

Google Tasks API は、ユーザーの Google ToDo リスト(Google Tasks)の **タスクリスト** と **タスク** を REST で読み書きするための API。

| 概念 | 説明 |
|---|---|
| Task List(タスクリスト) | タスクの入れ物。ユーザーは最低 1 つの「デフォルト」リストを持つ |
| Task(タスク) | 個々の ToDo。タイトル・メモ・期日・完了日時などを持つ。サブタスク(親子関係)も可 |

- ベース URL: `https://tasks.googleapis.com`
- Discovery ドキュメント: `https://www.googleapis.com/discovery/v1/apis/tasks/v1/rest`
- 公式クライアントライブラリ: Java / Python / PHP ほか(Node.js・Go なども Google API クライアントで利用可)
- 利用料金: 公式ドキュメントに料金の記載はない(無料枠の中でクォータが適用される)

---

## 2. 認証(OAuth 2.0)

### スコープ

| スコープ | 権限 |
|---|---|
| `https://www.googleapis.com/auth/tasks` | タスクの作成・編集・整理・削除(フルアクセス) |
| `https://www.googleapis.com/auth/tasks.readonly` | タスクの閲覧のみ |

> 必要最小限のスコープを選ぶことが推奨されている。読み取りだけなら `tasks.readonly`。

### 注意点

- Tasks は **個人ユーザーのデータ** なので、基本的には **ユーザーの OAuth 同意** を得たアクセストークンが必要。
  - サービスアカウントは「アプリ自身」として動作するため、そのままでは個人の Google アカウントのタスクにはアクセスできない(Google Workspace の場合はドメイン全体の委任という手段があるが、個人 Gmail アカウントでは使えない)。
- OAuth 同意画面のユーザータイプが **External** で公開ステータスが **Testing** のままだと、**リフレッシュトークンが 7 日で失効** する。常駐 Bot として長期運用するなら「本番公開(In production)」にするか、定期的に再認証する必要がある。
- リフレッシュトークンは 6 か月使われないと失効する場合があるほか、Google アカウント × OAuth クライアントあたり 100 個までで、超えると古いものから無効化される。
- 公開アプリとして外部ユーザーに使わせる場合は Google の検証プロセスが必要になる。

---

## 3. セットアップ手順(Python クイックスタート準拠)

1. **API を有効化**: Google Cloud Console でプロジェクトを作り、「Google Tasks API」を有効化。
2. **OAuth 同意画面を設定**: Google Auth platform → Branding でアプリ名・サポートメールを入力し、Audience を設定(個人利用なら External + テストユーザーに自分を追加)。
3. **認証情報の作成**: Google Auth platform → Clients で **デスクトップアプリ** タイプのクライアントを作成し、JSON をダウンロードして `credentials.json` として保存。
4. **ライブラリをインストール**:

```bash
python3 -m pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

5. **サンプル実行**: 初回はブラウザで認可 → `token.json` が保存され、以降は自動でリフレッシュされる。

```python
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# スコープを変更したら token.json を削除すること
SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]


def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("tasks", "v1", credentials=creds)
        results = service.tasklists().list(maxResults=10).execute()
        items = results.get("items", [])
        if not items:
            print("No task lists found.")
            return
        print("Task lists:")
        for item in items:
            print(f"{item['title']} ({item['id']})")
    except HttpError as err:
        print(err)


if __name__ == "__main__":
    main()
```

(出典: Google 公式 Python クイックスタート。Apache 2.0)

---

## 4. リソースとメソッド一覧

### 4.1 tasklists(タスクリスト)

| メソッド | HTTP | 説明 |
|---|---|---|
| list | `GET /tasks/v1/users/@me/lists` | 全タスクリスト取得 |
| get | `GET /tasks/v1/users/@me/lists/{tasklist}` | 指定リスト取得 |
| insert | `POST /tasks/v1/users/@me/lists` | リスト作成 |
| update | `PUT /tasks/v1/users/@me/lists/{tasklist}` | リスト更新(全置換) |
| patch | `PATCH /tasks/v1/users/@me/lists/{tasklist}` | リスト更新(部分) |
| delete | `DELETE /tasks/v1/users/@me/lists/{tasklist}` | リスト削除 |

> `{tasklist}` に `@default` を指定するとデフォルトリストを指せる。

**TaskList リソース**

```jsonc
{
  "kind": "tasks#taskList",  // 読み取り専用
  "id": "string",
  "etag": "string",
  "title": "string",         // 最大 1024 文字
  "updated": "string",       // RFC 3339, 読み取り専用
  "selfLink": "string"       // 読み取り専用
}
```

### 4.2 tasks(タスク)

| メソッド | HTTP | 説明 |
|---|---|---|
| list | `GET /tasks/v1/lists/{tasklist}/tasks` | リスト内のタスク一覧 |
| get | `GET /tasks/v1/lists/{tasklist}/tasks/{task}` | タスク取得 |
| insert | `POST /tasks/v1/lists/{tasklist}/tasks` | タスク作成 |
| update | `PUT /tasks/v1/lists/{tasklist}/tasks/{task}` | タスク更新(全置換) |
| patch | `PATCH /tasks/v1/lists/{tasklist}/tasks/{task}` | タスク更新(部分) |
| delete | `DELETE /tasks/v1/lists/{tasklist}/tasks/{task}` | タスク削除 |
| move | `POST /tasks/v1/lists/{tasklist}/tasks/{task}/move` | 並び替え・親変更・別リストへ移動 |
| clear | `POST /tasks/v1/lists/{tasklist}/clear` | 完了済みタスクを非表示化(hidden) |

**Task リソース**

```jsonc
{
  "kind": "tasks#task",      // 読み取り専用
  "id": "string",
  "etag": "string",
  "title": "string",         // 最大 1024 文字
  "updated": "string",       // RFC 3339, 読み取り専用
  "selfLink": "string",      // 読み取り専用
  "parent": "string",        // 親タスク ID(トップレベルなら省略)。読み取り専用 → 変更は move で
  "position": "string",      // 兄弟間の並び順キー(辞書順比較)。読み取り専用
  "notes": "string",         // 最大 8192 文字
  "status": "needsAction | completed",
  "due": "string",           // RFC 3339。※日付のみ保持、時刻は破棄される
  "completed": "string",     // 完了日時。未完了なら省略
  "deleted": false,
  "hidden": false,           // clear で非表示化された完了タスクは true。読み取り専用
  "links": [                 // 読み取り専用(Gmail 等から作られた場合の関連リンク)
    { "type": "email", "description": "string", "link": "string" }
  ],
  "webViewLink": "string",   // Google Tasks Web UI でタスクを開く URL。読み取り専用
  "assignmentInfo": { ... }  // Docs / Chat から割り当てられたタスクのみ。読み取り専用
}
```

#### 重要: `due` は「日付のみ」

> 公式: due は「タスクの予定日(カレンダーに表示される日)」であり締切時刻ではない。**日付部分のみが保存され時刻は破棄される。API から予定時刻を読み書きすることはできない。**

Google Tasks アプリ上で時刻付きで設定したタスクでも、API では `2026-10-16T00:00:00.000Z` のように 0 時(UTC)で返ってくる。時刻ベースのリマインドをしたい場合は、Bot 側で別途時刻を管理する(例: notes にメタ情報を書く / 独自 DB を持つ)などの工夫が必要。

### 4.3 tasks.list のクエリパラメータ

| パラメータ | 型 | 説明 | 既定値 |
|---|---|---|---|
| `maxResults` | int | 1 ページあたりの件数 | 20(最大 100) |
| `pageToken` | string | 次ページ取得用トークン | - |
| `completedMin` / `completedMax` | RFC 3339 | 完了日時の範囲で絞り込み | なし |
| `dueMin` / `dueMax` | RFC 3339 | 期日の範囲で絞り込み | なし |
| `updatedMin` | RFC 3339 | 指定日時以降に更新されたものだけ | なし |
| `showCompleted` | bool | 完了タスクを含めるか ※公式アプリで完了したタスクは `showHidden=true` も必要 | true |
| `showHidden` | bool | 非表示タスクを含めるか | false |
| `showDeleted` | bool | 削除済みタスクを含めるか | false |
| `showAssigned` | bool | Docs/Chat から割り当てられたタスクを含めるか | false |

レスポンス: `{ kind: "tasks#tasks", etag, nextPageToken, items: [Task...] }`

### 4.4 tasks.insert / tasks.move のパラメータ

- `insert`
  - `parent`: 親タスク ID(省略でトップレベル)
  - `previous`: 直前の兄弟タスク ID(省略で先頭)
- `move`
  - `parent`: 新しい親タスク ID(省略でトップレベルへ)
  - `previous`: 新しい直前の兄弟 ID(省略で先頭へ)
  - `destinationTasklist`: 移動先リスト ID(省略で同一リスト内)。※繰り返しタスクはリスト間移動不可
- 割り当てタスク・繰り返しタスクは親になれない/子にできない。

---

## 5. Python での主な操作例

```python
service = build("tasks", "v1", credentials=creds)

# タスクリスト一覧
lists = service.tasklists().list().execute().get("items", [])

# 未完了タスクを期日範囲で取得(ページング対応)
def list_tasks(tasklist_id, **kwargs):
    tasks, token = [], None
    while True:
        res = service.tasks().list(
            tasklist=tasklist_id, maxResults=100, pageToken=token, **kwargs
        ).execute()
        tasks += res.get("items", [])
        token = res.get("nextPageToken")
        if not token:
            return tasks

due_today = list_tasks(
    "@default",
    showCompleted=False,
    dueMin="2026-10-16T00:00:00Z",
    dueMax="2026-10-17T00:00:00Z",
)

# タスク作成
task = service.tasks().insert(
    tasklist="@default",
    body={"title": "レポート提出", "notes": "第3章まで", "due": "2026-10-20T00:00:00.000Z"},
).execute()

# 完了にする(部分更新)
service.tasks().patch(
    tasklist="@default", task=task["id"], body={"status": "completed"}
).execute()

# 未完了に戻す(completed を null にする)
service.tasks().patch(
    tasklist="@default", task=task["id"], body={"status": "needsAction", "completed": None}
).execute()

# 削除
service.tasks().delete(tasklist="@default", task=task["id"]).execute()

# 完了済みタスクを一括で非表示化
service.tasks().clear(tasklist="@default").execute()
```

### パフォーマンス Tips(公式)

- **部分レスポンス**: `fields` パラメータで必要なフィールドだけ取得
  例: `service.tasks().list(tasklist="@default", fields="items(id,title,due,status),nextPageToken")`
- **PATCH を使う**: 変更したいフィールドだけ送る。`null` を送るとフィールド削除。配列は丸ごと置換。
- **ETag**: `If-Match` ヘッダで楽観ロックが可能。
- **gzip**: `Accept-Encoding: gzip` で転送量削減。

---

## 6. 制限・クォータ

| 項目 | 値 |
|---|---|
| API 呼び出し | 1 日あたり 50,000 クエリ(courtesy limit。プロジェクトにより異なる、Cloud Console から増枠申請可) |
| 1 リストあたりの非表示でないタスク数 | 最大 20,000 |
| 1 ユーザーのタスク総数 | 最大 100,000 |
| タイトル | 最大 1024 文字 |
| メモ (notes) | 最大 8192 文字 |
| tasks.list の maxResults | 最大 100 |

- Docs / Chat スペースから割り当てられたタスクは API から作成できない(各アプリでの割り当てのみ)。
- 割り当てタスクを `delete` すると元のアイテムごと削除される点に注意。

---

## 7. リマインダー Bot を作る上での注意点・設計メモ

1. **プッシュ通知(Webhook / watch)は無い**
   Calendar API や Drive API と違い、Tasks API には `watch` メソッドが存在しない(公式リファレンスのメソッド一覧に無い)。変更検知は **ポーリング** で行う必要がある。
   - `updatedMin` を前回ポーリング時刻にして差分取得すると効率的。
   - 50,000 クエリ/日 ≒ 約 0.58 回/秒。リスト数 × ポーリング頻度で上限を見積もること(例: 5 リストを 1 分ごと → 7,200 回/日)。
2. **期日に時刻が無い**
   「◯時にリマインド」はできないので、「期日当日の朝に通知」「前日に通知」など日付単位の設計にするか、時刻情報を Bot 側で持つ。
   また `due` は UTC 0 時で返るため、JST(UTC+9)で日付比較する際は「日付部分だけ」を取り出して扱うのが安全。
3. **完了タスクの扱い**
   公式アプリで完了にしたタスクは hidden 扱いになることがあるため、完了タスクも取得したいときは `showCompleted=True, showHidden=True` を指定する。
4. **認証の運用**
   Discord Bot はサーバー常駐なので、初回のみローカルで `InstalledAppFlow` を実行して `token.json`(リフレッシュトークン)を作成 → サーバーに配置、という運用が簡単。
   ただし同意画面が「Testing」だと 7 日で失効するので、本番公開にしておく(個人利用で検証未完了でも、警告画面を経由して自分は認可可能)。
   `credentials.json` / `token.json` は Git にコミットしないこと。
5. **複数ユーザー対応する場合**
   Discord ユーザーごとに OAuth フローを回して各自のトークンを保存する必要がある(Web サーバーでのリダイレクト受け口 or デバイスフローなど)。単一ユーザー(自分用)なら上記 4 の方式で十分。
6. **非同期処理**
   `google-api-python-client` は同期(ブロッキング)ライブラリ。discord.py のイベントループ内で呼ぶ場合は `asyncio.to_thread(...)` などでスレッドに逃がす。

---

## 参考文献

### 公式ドキュメント
- Google Tasks API Overview — https://developers.google.com/workspace/tasks/overview
- REST Reference(リソース・メソッド一覧) — https://developers.google.com/workspace/tasks/reference/rest
- Task リソース — https://developers.google.com/workspace/tasks/reference/rest/v1/tasks
- TaskList リソース — https://developers.google.com/workspace/tasks/reference/rest/v1/tasklists
- tasks.list — https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list
- tasks.insert — https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/insert
- tasks.move — https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/move
- Python クイックスタート — https://developers.google.com/workspace/tasks/quickstart/python
- 認証・スコープ — https://developers.google.com/workspace/tasks/auth
- 使用量の上限 — https://developers.google.com/workspace/tasks/limits
- パフォーマンスのヒント — https://developers.google.com/workspace/tasks/performance
- Using OAuth 2.0 to Access Google APIs(リフレッシュトークンの失効条件) — https://developers.google.com/identity/protocols/oauth2
- Discovery ドキュメント — https://www.googleapis.com/discovery/v1/apis/tasks/v1/rest
- 公式サンプルコード(GitHub) — https://github.com/googleworkspace/python-samples/blob/main/tasks/quickstart/quickstart.py

### プッシュ通知が無いことに関する補足情報(非公式)
- Rollout: Quick guide to realtime data in Google Tasks without webhooks — https://rollout.com/integration-guides/google-tasks/quick-guide-to-realtime-data-in-google-tasks-without-webhooks
- Google Developer forums: Google Tasks API two-way sync is harder than I expected — https://discuss.google.dev/t/google-tasks-api-two-way-sync-is-harder-than-i-expected-how-are-others-handling-polling-and-quota-limits/357552
- Pipedream: Google Tasks triggers(内部的にポーリングしている例) — https://pipedream.com/apps/google-tasks/triggers/new-task-updated
