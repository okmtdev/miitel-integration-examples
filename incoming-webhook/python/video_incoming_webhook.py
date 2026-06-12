#!/usr/bin/env python3
"""MiiTel Meetings / Video (MM) Incoming Webhook クライアント (標準ライブラリのみ)。

MiiTel Phone の Incoming Webhook と同様に、外部の会議録画 (動画/音声) を
MiiTel Meetings に取り込むための 2 段階フロー。

  1. 会議メタデータを Video Incoming Webhook URL に POST する。
     MiiTel が会議履歴を生成し、メディアアップロード用の URL を返す。
  2. 返された URL に動画/音声ファイルをバイナリで PUT する。

Webhook URL / 認証トークンは MiiTel CS から払い出される値を使う。
メタデータは JSON ファイルから読み込むため、正確なフィールド仕様は
公式リファレンスに従って JSON を用意すればよい。

  仕様: https://developers.miitel.com/docs/video-incoming-webhook-getting-started
  API : https://developers.miitel.com/reference/videovideoincomingwebhookreceive

実行例:
  python video_incoming_webhook.py \
      --webhook-url "$MIITEL_VIDEO_IW_WEBHOOK_URL" \
      --token "$MIITEL_VIDEO_IW_TOKEN" \
      --metadata samples/video_data.json \
      --media ./meeting.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import miitel_common


# レスポンスからアップロード URL を探す際に候補となるキー名。
_UPLOAD_URL_KEYS = (
    "upload_url",
    "video_upload_url",
    "media_upload_url",
    "recording_upload_url",
    "url",
)


def _find_upload_url(obj: Any) -> str | None:
    """レスポンス JSON を再帰的に探索し、最初に見つかったアップロード URL を返す。"""
    if isinstance(obj, dict):
        for key in _UPLOAD_URL_KEYS:
            value = obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        for value in obj.values():
            found = _find_upload_url(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_upload_url(item)
            if found:
                return found
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("MIITEL_VIDEO_IW_WEBHOOK_URL"),
        help="MiiTel CS から払い出された Video Incoming Webhook URL (環境変数 MIITEL_VIDEO_IW_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MIITEL_VIDEO_IW_TOKEN"),
        help="Bearer 認証トークン (環境変数 MIITEL_VIDEO_IW_TOKEN)",
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="会議メタデータの JSON ファイル",
    )
    parser.add_argument(
        "--media",
        help="アップロードする動画/音声ファイルのパス",
    )
    parser.add_argument(
        "--upload-url-json-path",
        help=(
            "レスポンス内のアップロード URL の場所をドット区切りで明示指定する "
            "(例: data.upload_url)。未指定なら自動探索する。"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せずに、送るリクエスト内容だけを表示する。",
    )
    args = parser.parse_args(argv)

    if not args.webhook_url:
        parser.error("--webhook-url か環境変数 MIITEL_VIDEO_IW_WEBHOOK_URL が必要です。")

    with open(args.metadata, encoding="utf-8") as f:
        metadata = json.load(f)

    if args.dry_run:
        print("== POST (dry-run) ==")
        print(f"URL: {args.webhook_url}")
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        if args.media:
            print(f"\n== Media file ==\n  {args.media}")
        return 0

    # 1. メタデータを POST してメディアアップロード URL を取得する。
    print("会議メタデータを送信中...")
    try:
        resp = miitel_common.post_json(args.webhook_url, metadata, token=args.token)
    except miitel_common.HttpError as exc:
        print(f"メタデータ送信に失敗しました: {exc}", file=sys.stderr)
        return 1

    response_json = resp.json()
    print(f"レスポンス (HTTP {resp.status}):")
    print(json.dumps(response_json, ensure_ascii=False, indent=2))

    if not args.media:
        print("--media が未指定のため、アップロードはスキップします。")
        return 0

    # 2. アップロード URL を特定する。
    if args.upload_url_json_path:
        upload_url: Any = response_json
        for part in args.upload_url_json_path.split("."):
            if isinstance(upload_url, dict):
                upload_url = upload_url.get(part)
            else:
                upload_url = None
                break
    else:
        upload_url = _find_upload_url(response_json)

    if not isinstance(upload_url, str):
        print(
            "レスポンスからアップロード URL を取得できませんでした。"
            "--upload-url-json-path で場所を指定してください。",
            file=sys.stderr,
        )
        return 1

    # 3. メディアファイルを PUT する。
    print(f"メディアをアップロード中: {args.media}")
    try:
        put_resp = miitel_common.put_file(upload_url, args.media)
        print(f"  完了 (HTTP {put_resp.status})")
    except (miitel_common.HttpError, OSError) as exc:
        print(f"  アップロード失敗: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
