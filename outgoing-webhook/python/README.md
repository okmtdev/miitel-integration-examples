# MiiTel Outgoing Webhook サンプル (Python)

MiiTel が送信する **Outgoing Webhook（通話履歴）** を受信するサーバーの Python サンプルです。

- `server.py` … Webhook 受信サーバー（`http.server` ベース）
- `send_sample.py` … MiiTel を介さずローカルで動作確認するための送信クライアント

> **依存パッケージはありません。** Python 3.10 以降の標準ライブラリだけで動作します。

## Outgoing Webhook の仕組み

MiiTel Admin に設定した URL へ、MiiTel は以下のようなタイミングで HTTP POST を送信します。

- 通話履歴の（リアルタイム）文字起こし終了時
- 議事録作成完了時 / リアルタイム議事録作成完了時
- IVR 番号入力時、不在着信 / 不在発信時、自動転送先が不在時 など

開発者はこの Webhook を受信して、外部システムへ通話履歴情報を連携できます。

参考: [Outgoing Webhook 通話履歴の仕様と利用方法](https://developers.miitel.com/docs/outgoing-webhook-callhistory)

### HTTP リクエストの形

| 項目 | 値 |
| --- | --- |
| バージョン | HTTP/1.1 |
| メソッド | POST |
| `content-type` | `application/json; charset=utf-8` |
| `user-agent` | `MiiTel-Webhook/v1` |

ボディは `call`（`id` / `tenant_code` / `details[]`）を持つ JSON です。`details[]` には
通話種別・時刻・参加者・応対評価・文字起こし（`phrases` / `speech_recognition`）や、
議事録作成完了時は `minutes` が含まれます。

## このサーバーが対応していること

1. **Challenge-Response（設定保存時の確認）**
   MiiTel は設定保存時、ペイロードに `{"challenge": "hex_token"}` を付与して送信します。
   サーバーは **`Content-Type: text/plain` の 200 OK で `hex_token` のみ**を返す必要があります。
   本サーバーは `challenge` を検出すると自動でこの応答を返します。
2. **通常イベントの受信** … JSON を要約表示し、必要なら生ペイロードを保存します。
3. **冪等性（重複排除）** … Outgoing Webhook は**同じデータが複数回送信され得ます**
   （固定 IP 設定時は毎時 0/10/20/… 分に過去約 15 分を一括再送）。`call.details[].id`
   で重複を判定し、再送を正としてスキップします。
4. **任意の認証** … MiiTel の「追加ヘッダー」で Bearer / BASIC を設定した場合、その値を検証できます。

## 使い方

### 1. サーバーを起動する

```bash
cd outgoing-webhook/python

# 最小構成（ポート 8080 で待ち受け）
python3 server.py --port 8080

# 受信した生ペイロードを保存し、重複排除を永続化する
python3 server.py --port 8080 --save-dir ./received --dedupe-file ./seen.json

# MiiTel 側の「追加ヘッダー」で Authorization を設定した場合、その値を検証する
python3 server.py --port 8080 --auth-value "Bearer ACCESSTOKEN"
```

主なオプション（すべて環境変数でも指定可）:

| オプション | 環境変数 | 説明 |
| --- | --- | --- |
| `--host` | `MIITEL_OW_HOST` | 待ち受けホスト（既定: `0.0.0.0`） |
| `--port` | `MIITEL_OW_PORT` | 待ち受けポート（既定: `8080`） |
| `--auth-header` | `MIITEL_OW_AUTH_HEADER` | 検証する認証ヘッダー名（既定: `Authorization`） |
| `--auth-value` | `MIITEL_OW_AUTH_VALUE` | 認証ヘッダーの期待値。未指定なら検証しない |
| `--save-dir` | `MIITEL_OW_SAVE_DIR` | 生ペイロードの保存先。未指定なら保存しない |
| `--dedupe-file` | `MIITEL_OW_DEDUPE_FILE` | 重複排除の状態の永続化先。未指定ならメモリのみ |

`GET /health` で死活監視できます。

### 2. ローカルで動作確認する

別ターミナルから、サンプルを送って動作を確認します。

```bash
cd outgoing-webhook/python

# Challenge-Response（text/plain で hex_token のみ返ることを確認）
python3 send_sample.py --payload samples/challenge_payload.json

# 通常の通話履歴イベント
python3 send_sample.py --payload samples/transcription_payload.json

# もう一度同じものを送ると重複として検出される
python3 send_sample.py --payload samples/transcription_payload.json
```

curl でも確認できます:

```bash
curl -i -X POST http://127.0.0.1:8080/ \
  -H 'Content-Type: application/json' \
  --data @samples/challenge_payload.json
# => 200 / Content-Type: text/plain / body は hex_token のみ
```

### 3. MiiTel Admin に登録する

1. https://account.miitel.jp/v1/signin に管理者権限でログイン → MiiTel Admin
2. [外部連携] > [Outgoing Webhook] > [通話履歴連携設定を追加]
3. **URL** に本サーバーの公開 URL を設定（インターネットから到達可能である必要があります。
   ローカル検証時は ngrok 等のトンネルを利用してください）
4. 必要に応じて **追加ヘッダー**（例 `{"Authorization":"Bearer ACCESSTOKEN"}`）を設定し、
   サーバー側は `--auth-value "Bearer ACCESSTOKEN"` で一致させる
5. **通知ルール**を選び [保存] → このとき Challenge-Response が実行されます

> **NOTE:** `User-Agent` と `Content-Type` は MiiTel 側で固定のため、追加ヘッダーで指定しても反映されません。
> Challenge-Response が成立しないと設定を保存できません。

## ファイル構成

```
outgoing-webhook/python/
├── README.md                # このファイル
├── server.py                # 受信サーバー (http.server)
├── miitel_outgoing.py       # 検証・要約・重複排除・保存のヘルパー
├── send_sample.py           # ローカル動作確認用の送信クライアント
└── samples/
    ├── challenge_payload.json      # Challenge-Response 確認用
    └── transcription_payload.json  # 文字起こし終了時イベントのサンプル
```

## 補足（正直ベース）

- 本サーバーは MiiTel には常に `200` を返します（再送ループを避けるため）。受信後の処理を
  非同期化したい場合は `do_POST` 内の処理をキュー投入などに置き換えてください。
- `speech_recognition.summary`（要約文）は 2025-06-19 以降、非表示に変更されています。
- 議事録作成完了時のペイロードは `details[].minutes` を含みます。要約表示には対応していますが、
  必要に応じて `miitel_outgoing.summarize()` を拡張してください。
