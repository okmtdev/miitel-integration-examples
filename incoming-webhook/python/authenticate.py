#!/usr/bin/env python3
"""MiiTel Open API のアクセストークンを取得する (標準ライブラリのみ)。

Incoming Webhook の `Authorization: Bearer <token>` に使うアクセストークンは、
MiiTel Admin で発行した API 認証情報を使い、認証エンドポイントから取得する。

  POST https://{テナント}.miitel.jp/api/auth/v2/authenticate

  リファレンス: https://developers.miitel.com/reference/auth__authentication

認証情報 (company_id / access_key / access_secret など) は JSON ファイルから
読み込むため、正確なフィールド名は公式リファレンスに従って JSON を用意すればよい。

実行例:
  # 取得したトークンを環境変数へ
  export MIITEL_IW_TOKEN="$(python3 authenticate.py \
      --base-url https://example.miitel.jp \
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
        default=os.environ.get("MIITEL_BASE_URL"),
        help="テナントのベース URL (例: https://example.miitel.jp)。環境変数 MIITEL_BASE_URL。",
    )
    parser.add_argument(
        "--credentials",
        required=True,
        help="API 認証情報の JSON ファイル (MiiTel Admin で発行した値)",
    )
    args = parser.parse_args(argv)

    if not args.base_url:
        parser.error("--base-url か環境変数 MIITEL_BASE_URL が必要です。")

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
