#!/usr/bin/env python3
"""MiiTel Account のアクセストークンを取得する (標準ライブラリのみ)。

Incoming Webhook の `Authorization: Bearer <token>` に使うアクセストークンは、
MiiTel Account の認証エンドポイントから取得する。

  POST https://account.miitel.com/auth/v1/authenticate

  リファレンス: https://developers.miitel.com/reference/auth__authentication

認証ボディ (flow / params) は JSON ファイルから読み込む。
`flow` は `USER_PASSWORD` (email / password) か `REFRESH_TOKEN` を指定する。

実行例:
  # 取得したトークンを環境変数へ
  export MIITEL_IW_TOKEN="$(python3 authenticate.py \
      --credentials samples/auth_credentials.json)"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import miitel_common


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MIITEL_AUTH_BASE_URL", "https://account.miitel.com"),
        help="認証基盤のベース URL (既定: https://account.miitel.com)。環境変数 MIITEL_AUTH_BASE_URL。",
    )
    parser.add_argument(
        "--credentials",
        required=True,
        help="認証ボディ (flow / params) の JSON ファイル",
    )
    args = parser.parse_args(argv)

    with open(args.credentials, encoding="utf-8") as f:
        credentials = json.load(f)

    try:
        token = miitel_common.authenticate(args.base_url, credentials)
    except (miitel_common.HttpError, RuntimeError) as exc:
        print(f"認証に失敗しました: {exc}", file=sys.stderr)
        return 1

    # トークンだけを標準出力へ (`$(...)` で受け取りやすいように)。
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
