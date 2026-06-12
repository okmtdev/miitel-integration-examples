#!/usr/bin/env python3
"""MiiTel Phone (MP) Incoming Webhook クライアント (標準ライブラリのみ)。

Incoming Webhook は 2 段階で外部の通話録音を MiiTel に取り込む。

  1. 通話メタデータ (call_data) を Webhook URL に POST する。
     MiiTel が通話履歴を生成し、音声アップロード用の URL を返す。
  2. 返された URL に音声ファイルをバイナリで PUT する。

Webhook URL は MiiTel Admin で発行した値を使う (URL 自体が資格情報のため、
Webhook POST に認証ヘッダーは不要)。本スクリプトはメタデータを JSON ファイルから
読み込むだけなので、正確なフィールド仕様は公式リファレンスに従って JSON を用意する。

  仕様: https://developers.miitel.com/docs/incoming-webhook-getting-started
  API : https://developers.miitel.com/reference/call__webhook_call_creation

実行例:
  python phone_incoming_webhook.py \
      --webhook-url "$MIITEL_IW_WEBHOOK_URL" \
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


def _url_from(value: Any) -> str | None:
    """URL 文字列、または {"url": ...} 形式の dict から URL を取り出す。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url") or value.get("audio_upload_url")
    return None


def _extract_upload_urls(response_json: Any) -> dict[str, str]:
    """POST レスポンスから call_data_id -> アップロード URL の対応を取り出す。

    公式レスポンスは以下の形 (audio_upload_urls はリスト、各要素は
    call_data_id をキーに持つ dict)。

        {"audio_upload_urls": [
            {"<call_data_id>": {"url": "...", "call_id": "...", ...}}
        ]}

    list が dict のフラット形 ({"call_data_id": ..., "url": ...}) や、
    audio_upload_urls 自体が dict の場合も保険的に吸収する。
    """
    if not isinstance(response_json, dict):
        return {}

    raw = response_json.get("audio_upload_urls", response_json.get("upload_urls"))
    result: dict[str, str] = {}

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            # フラット形: {"call_data_id": id, "url": url}
            if "call_data_id" in item and ("url" in item or "audio_upload_url" in item):
                url = _url_from(item)
                if url:
                    result[str(item["call_data_id"])] = url
                continue
            # 公式形: {"<call_data_id>": {"url": ...}}
            for call_data_id, value in item.items():
                url = _url_from(value)
                if url:
                    result[call_data_id] = url
    elif isinstance(raw, dict):
        for call_data_id, value in raw.items():
            url = _url_from(value)
            if url:
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
        "--content-type",
        default=None,
        help="PUT 時の Content-Type。既定では付けない (署名付き URL のため)。",
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
            put_resp = miitel_common.put_file(url, path, content_type=args.content_type)
            print(f"  完了 (HTTP {put_resp.status})")
        except (miitel_common.HttpError, OSError) as exc:
            print(f"  アップロード失敗: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
