#!/usr/bin/env python3
"""ローカルの受信サーバーへサンプルペイロードを送る確認用クライアント (標準ライブラリのみ)。

MiiTel を介さずに server.py の動作を確認するためのもの。

実行例:
  python3 send_sample.py --url http://127.0.0.1:8080/ --payload samples/transcription_payload.json
  python3 send_sample.py --payload samples/challenge_payload.json   # Challenge-Response の確認
"""

from __future__ import annotations

import argparse
import urllib.request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8080/", help="送信先 URL (既定: http://127.0.0.1:8080/)")
    parser.add_argument("--payload", required=True, help="送信する JSON ファイル")
    parser.add_argument("--auth-value", help='付与する認証ヘッダー値 (例: "Bearer ACCESSTOKEN")')
    parser.add_argument("--auth-header", default="Authorization", help="認証ヘッダー名 (既定: Authorization)")
    args = parser.parse_args(argv)

    with open(args.payload, "rb") as f:
        data = f.read()

    # MiiTel 本番と同じヘッダーを模倣する。
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "MiiTel-Webhook/v1",
    }
    if args.auth_value:
        headers[args.auth_header] = args.auth_value

    request = urllib.request.Request(args.url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request) as resp:
        print(f"HTTP {resp.status}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        print(resp.read().decode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
