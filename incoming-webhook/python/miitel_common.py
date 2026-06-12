"""MiiTel Incoming Webhook 用の共通ユーティリティ。

標準ライブラリ (urllib) だけで HTTP リクエストを行うための薄いヘルパー群です。
MiiTel Phone (MP) / MiiTel Meetings (MM) 双方の Incoming Webhook スクリプトから
利用します。
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


# 拡張子から Content-Type を引けないファイル向けのフォールバック。
_CONTENT_TYPE_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


@dataclass
class HttpResponse:
    """HTTP レスポンスの最小表現。"""

    status: int
    body: bytes
    headers: Mapping[str, str]

    def json(self) -> Any:
        """レスポンスボディを JSON としてパースして返す。"""
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpError(RuntimeError):
    """4xx / 5xx などの HTTP エラーを表す例外。"""

    def __init__(self, status: int, body: str, url: str) -> None:
        super().__init__(f"HTTP {status} for {url}: {body}")
        self.status = status
        self.body = body
        self.url = url


def guess_content_type(path: str) -> str:
    """ファイルパスから Content-Type を推測する。"""
    guessed, _ = mimetypes.guess_type(path)
    if guessed:
        return guessed
    for ext, content_type in _CONTENT_TYPE_BY_EXT.items():
        if path.lower().endswith(ext):
            return content_type
    return "application/octet-stream"


def _request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 60.0,
    max_retries: int = 3,
) -> HttpResponse:
    """urllib を使った汎用リクエスト。ネットワーク/5xx エラー時はリトライする。"""
    headers = dict(headers or {})
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return HttpResponse(
                    status=resp.status,
                    body=resp.read(),
                    headers={k: v for k, v in resp.headers.items()},
                )
        except urllib.error.HTTPError as exc:  # 4xx / 5xx
            body = exc.read().decode("utf-8", errors="replace")
            # 4xx はリクエスト内容の問題なのでリトライしない。
            if exc.code < 500 or attempt == max_retries:
                raise HttpError(exc.code, body, url) from exc
            last_error = HttpError(exc.code, body, url)
        except urllib.error.URLError as exc:  # 接続失敗・タイムアウト等
            last_error = exc
            if attempt == max_retries:
                raise

        # 指数バックオフ: 2s, 4s, 8s ...
        time.sleep(2 ** (attempt + 1))

    # ここには通常到達しないが、型・安全のため。
    assert last_error is not None
    raise last_error


def post_json(
    url: str,
    payload: Any,
    *,
    token: str | None = None,
    basic_auth: tuple[str, str] | None = None,
    extra_headers: Mapping[str, str] | None = None,
    timeout: float = 60.0,
) -> HttpResponse:
    """JSON ボディを POST する。

    認証は Bearer トークンか BASIC 認証のどちらかを指定できる。
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if basic_auth:
        import base64

        user, password = basic_auth
        raw = f"{user}:{password}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    if extra_headers:
        headers.update(extra_headers)

    body = json.dumps(payload).encode("utf-8")
    return _request("POST", url, data=body, headers=headers, timeout=timeout)


def put_file(
    url: str,
    file_path: str,
    *,
    content_type: str | None = None,
    timeout: float = 300.0,
) -> HttpResponse:
    """事前署名済み URL などにファイルをバイナリ PUT する。

    MiiTel が返す URL は署名付きのため、署名対象外のヘッダーを足すと 403 に
    なり得る。公式チュートリアルに倣い、既定では Content-Type を付けない。
    必要な場合のみ `content_type` を明示する。
    """
    with open(file_path, "rb") as f:
        data = f.read()
    headers = {"Content-Type": content_type} if content_type else {}
    return _request("PUT", url, data=data, headers=headers, timeout=timeout)


# レスポンスからアクセストークンを探す際に候補となるキー名。
_TOKEN_KEYS = ("access_token", "token", "accessToken")


def authenticate(
    base_url: str,
    credentials: Mapping[str, Any],
    *,
    path: str = "/auth/v1/authenticate",
    timeout: float = 60.0,
) -> str:
    """MiiTel Account の認証エンドポイントへ POST してアクセストークンを返す。

    `base_url` は認証基盤の URL (通常 https://account.miitel.com)。
    `credentials` は認証フローと認証パラメータをそのまま渡す。例:

        {"flow": "USER_PASSWORD",
         "params": {"email": "you@example.com", "password": "..."}}

    `flow` は `USER_PASSWORD` (email / password) か `REFRESH_TOKEN`
    (refresh_token) を指定できる。`params.client_id` は省略可能。

    リファレンス: https://developers.miitel.com/reference/auth__authentication
    """
    url = base_url.rstrip("/") + path
    resp = post_json(url, dict(credentials), timeout=timeout)
    data = resp.json()
    if isinstance(data, dict):
        for key in _TOKEN_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        # ネストしている場合 (例: {"data": {"access_token": ...}}) も探す。
        for value in data.values():
            if isinstance(value, dict):
                for key in _TOKEN_KEYS:
                    nested = value.get(key)
                    if isinstance(nested, str) and nested:
                        return nested
    raise RuntimeError(
        "認証レスポンスからアクセストークンを取得できませんでした: " + resp.text()
    )
