"""MiiTel Outgoing Webhook (通話履歴) 受信処理のヘルパー (標準ライブラリのみ)。

server.py から利用する。Webhook の検証 (Challenge-Response)、ペイロードの要約、
冪等性のための重複排除、生ペイロードの保存などを提供する。

  仕様: https://developers.miitel.com/docs/outgoing-webhook-callhistory
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any


def extract_challenge(payload: Any) -> str | None:
    """設定保存時の Challenge-Response 用 hex_token を取り出す (なければ None)。

    設定保存時、MiiTel は通常のペイロードに `{"challenge": "hex_token"}` を付与して
    送信する。サーバーは Content-Type: text/plain の 200 で hex_token のみを返す必要がある。
    """
    if isinstance(payload, dict):
        challenge = payload.get("challenge")
        if isinstance(challenge, str) and challenge:
            return challenge
    return None


def dedupe_ids(payload: Any) -> list[str]:
    """冪等性キーに使う ID を取り出す。

    通話履歴 (call) は details[].id、会議履歴 (video) は video.id を使う。
    """
    ids: list[str] = []
    if not isinstance(payload, dict):
        return ids
    call = payload.get("call")
    if isinstance(call, dict):
        for detail in call.get("details", []) or []:
            if isinstance(detail, dict) and isinstance(detail.get("id"), str):
                ids.append(detail["id"])
    video = payload.get("video")
    if isinstance(video, dict) and isinstance(video.get("id"), str):
        ids.append(video["id"])
    return ids


def summarize(payload: Any) -> str:
    """ペイロードを人が読める 1 件のサマリ文字列にする (通話履歴 / 会議履歴 両対応)。"""
    if not isinstance(payload, dict):
        return "(JSON オブジェクトではないペイロード)"
    if isinstance(payload.get("call"), dict):
        return _summarize_call(payload["call"])
    if isinstance(payload.get("video"), dict):
        return _summarize_video(payload["video"])
    return "(call / video フィールドがありません)"


def _summarize_call(call: dict) -> str:
    """通話履歴 (MiiTel Phone) のサマリ。"""
    lines = [f"[通話履歴] call.id={call.get('id')} tenant_code={call.get('tenant_code')}"]
    for detail in call.get("details", []) or []:
        if not isinstance(detail, dict):
            continue
        # 文字起こし終了時は phrases/speech_recognition/analysis、
        # 議事録作成完了時は minutes を含む。
        kinds = []
        if detail.get("phrases") is not None or detail.get("speech_recognition") is not None:
            kinds.append("文字起こし")
        if detail.get("minutes") is not None:
            kinds.append("議事録")
        kind = "/".join(kinds) or "イベント"

        participants = detail.get("participants") or []
        names = [
            f"{p.get('from_to')}:{p.get('name') or p.get('login_id') or '-'}"
            for p in participants
            if isinstance(p, dict)
        ]
        lines.append(
            f"  [{kind}] detail.id={detail.get('id')} "
            f"call_type={detail.get('call_type')} "
            f"from={detail.get('from_number')} to={detail.get('to_number')} "
            f"参加者=[{', '.join(names)}]"
        )
    return "\n".join(lines)


def _summarize_video(video: dict) -> str:
    """会議履歴 (MiiTel Meetings) のサマリ。"""
    # 文字起こし完了時は speech_recognition、議事録作成完了時は summary を含む。
    kinds = []
    if video.get("speech_recognition") is not None:
        kinds.append("文字起こし")
    if video.get("summary") is not None:
        kinds.append("議事録")
    kind = "/".join(kinds) or "イベント"

    host = video.get("host") or {}
    host_name = host.get("user_name") or host.get("login_id") or "-" if isinstance(host, dict) else "-"
    participants = video.get("participants") or []
    names = [
        p.get("miitel_user_name") or p.get("display_name") or "-"
        for p in participants
        if isinstance(p, dict)
    ]
    return (
        f"[会議履歴] [{kind}] video.id={video.get('id')} "
        f"tenant_code={video.get('tenant_code')}\n"
        f"  title={video.get('title')!r} platform={video.get('platform')} "
        f"host={host_name}\n"
        f"  starts_at={video.get('starts_at')} ends_at={video.get('ends_at')} "
        f"参加者=[{', '.join(names)}]"
    )


class Dedupe:
    """detail id を記録して重複イベントを判定する (スレッドセーフ)。

    Outgoing Webhook は同じデータが複数回送信され得る (固定 IP 設定時は 10 分毎に
    過去約 15 分を一括再送)。重複は再送として正とし、二重処理を避けるために使う。
    `path` を指定するとプロセス再起動をまたいで永続化する。
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._seen = set(json.load(f))
            except (OSError, ValueError):
                self._seen = set()

    def filter_new(self, ids: list[str]) -> tuple[list[str], list[str]]:
        """(初めて見た id, 重複していた id) を返し、内部状態を更新する。"""
        new: list[str] = []
        dup: list[str] = []
        with self._lock:
            for i in ids:
                if i in self._seen:
                    dup.append(i)
                else:
                    self._seen.add(i)
                    new.append(i)
            if self.path and new:
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(sorted(self._seen), f)
                os.replace(tmp, self.path)
        return new, dup


def save_payload(save_dir: str, payload: Any, raw: bytes) -> str:
    """生ペイロードを save_dir に保存し、保存先パスを返す。"""
    os.makedirs(save_dir, exist_ok=True)
    event_id = "unknown"
    if isinstance(payload, dict):
        for key in ("call", "video"):
            obj = payload.get(key)
            if isinstance(obj, dict) and obj.get("id"):
                event_id = obj["id"]
                break
    filename = f"{int(time.time() * 1000)}_{event_id}.json"
    path = os.path.join(save_dir, filename)
    with open(path, "wb") as f:
        f.write(raw)
    return path
