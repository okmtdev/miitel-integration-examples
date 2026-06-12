#!/usr/bin/env python3
"""MiiTel Phone (MP) Incoming Webhook クライアント (標準ライブラリのみ)。

Incoming Webhook は 2 段階で外部の通話録音を MiiTel に取り込む。

  1. 通話メタデータ (call_data) を Webhook URL に POST する。
     MiiTel が通話履歴を生成し、音声アップロード用の URL を返す。
  2. 返された URL に音声ファイルをバイナリで PUT する。

Webhook URL / 認証トークンは MiiTel CS から払い出される値を使う。
本スクリプトはメタデータを JSON ファイルから読み込むだけなので、
正確なフィールド仕様は公式リファレンスに従って JSON を用意すればよい。

  仕様: https://developers.miitel.com/docs/incoming-webhook-getting-started
  API : https://developers.miitel.com/reference/call__webhook_call_creation

実行例:
  python phone_incoming_webhook.py \
      --webhook-url "$MIITEL_IW_WEBHOOK_URL" \
      --token "$MIITEL_IW_TOKEN" \
      --metadata samples/phone_call_data.json \
      --audio test_id=./recording.mp3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import miitel_common


def _parse_audio_args(pairs: list[str]) -> dict[str, str]:
    """`call_data_id=/path/to/file` 形式の引数を辞書にする。"""
    mapping: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(
                f"--audio は 'call_data_id=path' 形式で指定してください: {pair!r}"
            )
        call_data_id, path = pair.split("=", 1)
        mapping[call_data_id.strip()] = path.strip()
    return mapping


def _extract_upload_urls(response_json: Any) -> dict[str, str]:
    """POST レスポンスから call_data_id -> アップロード URL の対応を取り出す。

    MiiTel のレスポンス構造の揺れ (list / dict、キー名) を吸収する。
    """
    if not isinstance(response_json, dict):
        return {}

    raw = response_json.get("audio_upload_urls", response_json.get("upload_urls"))
    result: dict[str, str] = {}

    if isinstance(raw, dict):
        # {"<call_data_id>": "<url>"} もしくは {"<call_data_id>": {"audio_upload_url": ...}}
        for call_data_id, value in raw.items():
            if isinstance(value, str):
                result[call_data_id] = value
            elif isinstance(value, dict):
                url = value.get("audio_upload_url") or value.get("url")
                if url:
                    result[call_data_id] = url
    elif isinstance(raw, list):
        # [{"call_data_id": ..., "audio_upload_url": ...}, ...]
        for item in raw:
            if not isinstance(item, dict):
                continue
            call_data_id = item.get("call_data_id")
            url = item.get("audio_upload_url") or item.get("url")
            if call_data_id and url:
                result[call_data_id] = url

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("MIITEL_IW_WEBHOOK_URL"),
        help="MiiTel CS から払い出された Incoming Webhook URL (環境変数 MIITEL_IW_WEBHOOK_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MIITEL_IW_TOKEN"),
        help="Bearer 認証トークン (環境変数 MIITEL_IW_TOKEN)",
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help='通話メタデータの JSON ファイル ({"call_data": [...]})',
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        metavar="call_data_id=PATH",
        help="アップロードする音声ファイル。複数指定可。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せずに、送るリクエスト内容だけを表示する。",
    )
    args = parser.parse_args(argv)

    if not args.webhook_url:
        parser.error("--webhook-url か環境変数 MIITEL_IW_WEBHOOK_URL が必要です。")

    with open(args.metadata, encoding="utf-8") as f:
        metadata = json.load(f)

    audio_files = _parse_audio_args(args.audio)

    if args.dry_run:
        print("== POST (dry-run) ==")
        print(f"URL: {args.webhook_url}")
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        print("\n== Audio files ==")
        for call_data_id, path in audio_files.items():
            print(f"  {call_data_id} -> {path}")
        return 0

    # 1. メタデータを POST して音声アップロード URL を取得する。
    print("通話メタデータを送信中...")
    try:
        resp = miitel_common.post_json(args.webhook_url, metadata, token=args.token)
    except miitel_common.HttpError as exc:
        print(f"メタデータ送信に失敗しました: {exc}", file=sys.stderr)
        return 1

    response_json = resp.json()
    print(f"レスポンス (HTTP {resp.status}):")
    print(json.dumps(response_json, ensure_ascii=False, indent=2))

    upload_urls = _extract_upload_urls(response_json)
    if not upload_urls:
        print(
            "レスポンスからアップロード URL を取得できませんでした。"
            "上記のレスポンスを確認してください。",
            file=sys.stderr,
        )
        return 1

    # 2. 音声ファイルをアップロード URL へ PUT する。
    exit_code = 0
    for call_data_id, url in upload_urls.items():
        path = audio_files.get(call_data_id)
        if not path:
            print(f"[skip] call_data_id={call_data_id} に対応する音声ファイル未指定。")
            continue
        print(f"音声をアップロード中: {call_data_id} <- {path}")
        try:
            put_resp = miitel_common.put_file(url, path)
            print(f"  完了 (HTTP {put_resp.status})")
        except (miitel_common.HttpError, OSError) as exc:
            print(f"  アップロード失敗: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
