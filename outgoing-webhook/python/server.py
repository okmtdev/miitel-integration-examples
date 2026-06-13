#!/usr/bin/env python3
"""MiiTel Outgoing Webhook (通話履歴) 受信サーバー (標準ライブラリのみ)。

MiiTel Admin の [外部連携] > [Outgoing Webhook] に設定した URL へ、MiiTel は
文字起こし終了時や議事録作成完了時などに HTTP POST を送信する。本サーバーは
それを受信し、内容を表示・保存する最小実装。

主な対応:
  - Challenge-Response: 設定保存時に届く {"challenge": "hex_token"} に対し、
    Content-Type: text/plain の 200 で hex_token のみを返す。
  - 通常イベント: JSON を要約表示し、必要なら生ペイロードを保存する。
  - 冪等性: 同一データが複数回届くため、detail id で重複を判定する。
  - 任意の認証: 追加ヘッダー (Bearer / BASIC) を設定した場合の検証。

  仕様: https://developers.miitel.com/docs/outgoing-webhook-callhistory

実行例:
  python3 server.py --port 8080
  # 認証ヘッダーを検証する場合 (MiiTel 側の追加ヘッダーと一致させる)
  python3 server.py --port 8080 --auth-value "Bearer ACCESSTOKEN"
  # 生ペイロードを保存し、重複排除を永続化する場合
  python3 server.py --save-dir ./received --dedupe-file ./seen.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import miitel_outgoing as ow


class WebhookHandler(BaseHTTPRequestHandler):
    # MiiTel は HTTP/1.1 で送信する。
    protocol_version = "HTTP/1.1"
    server_version = "MiiTelOutgoingWebhookSample/1.0"

    # main() から注入する設定。
    auth_header_name: str = "Authorization"
    expected_auth: str | None = None
    dedupe: ow.Dedupe | None = None
    save_dir: str | None = None

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/json; charset=utf-8") -> None:
        # エラー時は keep-alive を切る (本文未読などでストリームが不整合になり得るため)。
        if status >= 400:
            self.close_connection = True
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            # 応答書き込み中に接続が切れてもハンドラスレッドを落とさない。
            self.log_message("response write failed: %s", exc)

    def do_GET(self) -> None:
        # 死活監視用。
        if self.path in ("/health", "/healthz"):
            self._send(200, b'{"status":"ok"}')
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self) -> None:
        # Content-Length を安全にパースする (不正値で落とさない)。
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, b'{"error":"invalid content-length"}')
            return
        if length < 0:
            length = 0

        # 本文を読む。接続断時は応答できないので静かに終了する。
        try:
            raw = self.rfile.read(length) if length > 0 else b""
        except (ConnectionError, OSError) as exc:
            self.log_message("request read failed: %s", exc)
            return

        # 任意の認証検証 (MiiTel の「追加ヘッダー」を設定した場合)。
        if self.expected_auth is not None:
            if self.headers.get(self.auth_header_name) != self.expected_auth:
                self._send(401, b'{"error":"unauthorized"}')
                return

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, b'{"error":"invalid json"}')
            return

        # 1. Challenge-Response (設定保存時の確認)。
        challenge = ow.extract_challenge(payload)
        if challenge is not None:
            self.log_message("challenge-response: hex_token を返却")
            self._send(200, challenge.encode("utf-8"), content_type="text/plain")
            return

        # 2. 通常の Webhook イベント (通話履歴 call / 会議履歴 video)。
        #    保存や重複排除でファイル I/O 例外が出ても応答を返す
        #    (応答せずスレッドが落ちると MiiTel の再送ループを招くため)。
        try:
            self._handle_event(payload, raw)
        except Exception:  # noqa: BLE001 - サンプルとして握りつぶし 500 で再送に委ねる
            self.log_message("event handling failed:\n%s", traceback.format_exc())
            self._send(500, b'{"error":"internal"}')
            return

        # 正常時は 200 を返す。
        self._send(200, b'{"status":"received"}')

    def _handle_event(self, payload: object, raw: bytes) -> None:
        ids = ow.dedupe_ids(payload)
        if self.dedupe is not None:
            new_ids, dup_ids = self.dedupe.filter_new(ids)
        else:
            new_ids, dup_ids = ids, []

        print(ow.summarize(payload), flush=True)
        if dup_ids:
            print(f"  (重複 ID を {len(dup_ids)} 件検出: 再送とみなしスキップ)", flush=True)
        if self.save_dir and new_ids:
            saved = ow.save_payload(self.save_dir, payload, raw)
            print(f"  保存: {saved}", flush=True)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - - %s\n" % (self.address_string(), fmt % args))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("MIITEL_OW_HOST", "0.0.0.0"), help="待ち受けホスト (既定: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MIITEL_OW_PORT", "8080")), help="待ち受けポート (既定: 8080)")
    parser.add_argument(
        "--auth-header",
        default=os.environ.get("MIITEL_OW_AUTH_HEADER", "Authorization"),
        help="検証する認証ヘッダー名 (既定: Authorization)",
    )
    parser.add_argument(
        "--auth-value",
        default=os.environ.get("MIITEL_OW_AUTH_VALUE"),
        help='認証ヘッダーの期待値 (例: "Bearer ACCESSTOKEN")。未指定なら検証しない。',
    )
    parser.add_argument(
        "--save-dir",
        default=os.environ.get("MIITEL_OW_SAVE_DIR"),
        help="受信した生ペイロードを保存するディレクトリ。未指定なら保存しない。",
    )
    parser.add_argument(
        "--dedupe-file",
        default=os.environ.get("MIITEL_OW_DEDUPE_FILE"),
        help="重複排除の状態を永続化するファイル。未指定ならメモリ上のみ。",
    )
    args = parser.parse_args(argv)

    WebhookHandler.auth_header_name = args.auth_header
    WebhookHandler.expected_auth = args.auth_value
    WebhookHandler.save_dir = args.save_dir
    WebhookHandler.dedupe = ow.Dedupe(args.dedupe_file)

    httpd = ThreadingHTTPServer((args.host, args.port), WebhookHandler)
    print(f"MiiTel Outgoing Webhook サーバーを起動: http://{args.host}:{args.port}", flush=True)
    if args.auth_value:
        print(f"認証ヘッダー検証: 有効 ({args.auth_header})", flush=True)
    print("停止するには Ctrl+C", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止します。", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
