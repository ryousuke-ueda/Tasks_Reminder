"""Google OAuth 2.0 の認可とトークン管理。

サーバーにブラウザが無くても認可できるよう、次の手順を Discord 上で行う。
1. Bot が認可 URL を送る
2. ユーザーが手元のブラウザで開いて許可する
3. http://localhost/?code=... へリダイレクトされる（ページは開けなくてよい）
4. そのアドレスバーの URL を Bot に貼り付ける
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]
REDIRECT_URI = "http://localhost"


class AuthError(Exception):
    """認可が必要、または認可に失敗した。メッセージはそのままユーザーに表示する。"""


def extract_code(response: str) -> str:
    """リダイレクト先 URL（またはコードそのもの）から認可コードを取り出す。"""
    text = response.strip()
    if not text:
        raise AuthError("入力が空です。リダイレクト先の URL を貼り付けてください。")
    if "://" not in text:
        return text

    query = parse_qs(urlparse(text).query)
    if "error" in query:
        raise AuthError(f"Google 側で認可が拒否されました: {query['error'][0]}")
    codes = query.get("code")
    if not codes:
        raise AuthError("URL に認可コード（code=...）が含まれていません。")
    return codes[0]


class GoogleAuth:
    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._pending_flow: Flow | None = None

    @property
    def credentials_path(self) -> Path:
        return self._credentials_path

    def has_client_secrets(self) -> bool:
        return self._credentials_path.exists()

    def has_token(self) -> bool:
        return self._token_path.exists()

    def load_credentials(self) -> Credentials:
        """有効な認証情報を返す。期限切れなら更新する（通信が発生するのでスレッドで呼ぶこと）。"""
        if not self._token_path.exists():
            raise AuthError("Google アカウントが未連携です。")

        creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)
        if creds.valid:
            return creds
        if not creds.refresh_token:
            raise AuthError("保存されたトークンにリフレッシュトークンがありません。")
        try:
            creds.refresh(Request())
        except RefreshError as e:
            log.warning("トークンの更新に失敗: %s", e)
            raise AuthError("Google のトークンが失効しています。") from e
        self._save(creds)
        return creds

    def start_authorization(self) -> str:
        if not self.has_client_secrets():
            raise AuthError(f"OAuth クライアントの JSON がありません: {self._credentials_path}")
        flow = Flow.from_client_secrets_file(str(self._credentials_path), scopes=SCOPES, redirect_uri=REDIRECT_URI)
        # prompt=consent で毎回リフレッシュトークンを確実に受け取る
        url, _state = flow.authorization_url(access_type="offline", prompt="consent")
        self._pending_flow = flow
        return url

    def finish_authorization(self, response: str) -> None:
        """認可コードをトークンに交換して保存する（通信が発生するのでスレッドで呼ぶこと）。"""
        flow = self._pending_flow
        if flow is None:
            raise AuthError("認可が開始されていません。もう一度 /google_auth を実行してください。")
        code = extract_code(response)
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            log.warning("トークンの取得に失敗: %s", e)
            raise AuthError(
                "トークンの取得に失敗しました。コードの有効期限切れの可能性があるので、"
                "もう一度 /google_auth からやり直してください。"
            ) from e
        self._save(flow.credentials)
        self._pending_flow = None

    def _save(self, creds: Credentials) -> None:
        tmp = self._token_path.with_suffix(".tmp")
        tmp.write_text(creds.to_json(), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self._token_path)
