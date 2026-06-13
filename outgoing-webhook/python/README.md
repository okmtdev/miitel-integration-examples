# MiiTel Outgoing Webhook サンプル (Python)

MiiTel が送信する **Outgoing Webhook** を受信するサーバーの Python サンプルです。
**通話履歴（MiiTel Phone）** と **会議履歴（MiiTel Meetings）** の両方を 1 つのサーバーで受信できます。

- `server.py` … Webhook 受信サーバー（`http.server` ベース）
- `send_sample.py` … MiiTel を介さずローカルで動作確認するための送信クライアント

> **依存パッケージはありません。** Python 3.10 以降の標準ライブラリだけで動作します。

## Outgoing Webhook の仕組み

MiiTel Admin に設定した URL へ、MiiTel は以下のようなタイミングで HTTP POST を送信します。

**通話履歴（call）**
- 通話履歴の（リアルタイム）文字起こし終了時
- 議事録作成完了時 / リアルタイム議事録作成完了時
- IVR 番号入力時、不在着信 / 不在発信時、自動転送先が不在時 など

**会議履歴（video）**
- 文字起こし完了時（ペイロードに `speech_recognition` が含まれる）
- 議事録作成完了時（`speech_recognition` の代わりに `summary` が含まれる）

開発者はこの Webhook を受信して、外部システムへ通話 / 会議履歴情報を連携できます。

参考: [通話履歴の仕様](https://developers.miitel.com/docs/outgoing-webhook-callhistory) / [会議履歴の仕様](https://developers.miitel.com/docs/outgoing-webhook-meetinghistory)

### HTTP リクエストの形（通話履歴・会議履歴 共通）

| 項目 | 値 |
| --- | --- |
| バージョン | HTTP/1.1 |
| メソッド | POST |
| `content-type` | `application/json; charset=utf-8` |
| `user-agent` | `MiiTel-Webhook/v1` |

- **通話履歴**: ボディは `call`（`id` / `tenant_code` / `details[]`）。`details[]` に通話種別・時刻・
  参加者・応対評価・文字起こし（`phrases` / `speech_recognition`）、議事録作成完了時は `minutes` を含む。
- **会議履歴**: ボディは `video`（`id` / `tenant_code` / `title` / `platform` / `host` / `participants[]` …）。
  文字起こし完了時は `speech_recognition`、議事録作成完了時は `summary`（`template_type` / `raw`）を含む。
  > `speech_recognition.summary` は 2025-06-19 以降は常に空文字列 `""` で、AI 要約は別階層の `summary` フィールドで届きます。

## このサーバーが対応していること

1. **Challenge-Response（設定保存時の確認）**
   MiiTel は設定保存時、ペイロードに `{"challenge": "hex_token"}` を付与して送信します。
   サーバーは **`Content-Type: text/plain` の 200 OK で `hex_token` のみ**を返す必要があります。
   本サーバーは `challenge` を検出すると自動でこの応答を返します。
2. **通常イベントの受信** … JSON を要約表示し、必要なら生ペイロードを保存します。
3. **冪等性（重複排除）** … Outgoing Webhook は**同じデータが複数回送信され得ます**
   （通話履歴では固定 IP 設定時に毎時 0/10/20/… 分に過去約 15 分を一括再送）。
   通話履歴は `call.details[].id`、会議履歴は `video.id` で重複を判定し、再送を正としてスキップします。
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

# 通話履歴イベント（文字起こし終了時）
python3 send_sample.py --payload samples/transcription_payload.json

# 会議履歴イベント（文字起こし完了時 / 議事録作成完了時）
python3 send_sample.py --payload samples/video_transcription_payload.json
python3 send_sample.py --payload samples/video_summary_payload.json

# もう一度同じものを送ると重複として検出される
python3 send_sample.py --payload samples/transcription_payload.json

# 認証ヘッダーを検証する構成 (--auth-value 付きで起動した場合) の確認
python3 send_sample.py --auth-value "Bearer ACCESSTOKEN" --payload samples/transcription_payload.json
```

curl でも確認できます:

```bash
curl -i -X POST http://127.0.0.1:8080/ \
  -H 'Content-Type: application/json' \
  --data @samples/challenge_payload.json
# => 200 / Content-Type: text/plain / body は hex_token のみ
```

> **NOTE:** challenge や通常イベントのペイロードには、MiiTel 側で設定した**追加ペイロード
> （例 `params_key`）など想定外のフィールドが含まれることがあります**が、無視して問題ありません
> （本サーバーは必要なフィールドのみを参照します）。

### 3. ngrok でローカルサーバーを公開する（手元で MiiTel から受ける）

MiiTel はインターネットから到達できる URL にしか送信できません。手元の PC で動かす
サーバーを MiiTel に受けさせるには、[ngrok](https://ngrok.com/) などのトンネルで公開します。

```bash
# 1) サーバーを起動（例: ポート 8080）
python3 server.py --port 8080

# 2) 別ターミナルで ngrok を起動し、同じポートを公開する
ngrok http 8080
```

ngrok が表示する転送先 URL（例: `https://xxxx-xxxx.ngrok-free.app`）を控えます。
この URL が、次の手順で MiiTel Admin に設定する Webhook URL です。

```
Forwarding  https://xxxx-xxxx.ngrok-free.app -> http://localhost:8080
```

動作確認:

```bash
# 公開 URL に対して疎通確認（別ターミナル）
curl -i https://xxxx-xxxx.ngrok-free.app/health
# Challenge-Response も公開 URL 経由で試せる
python3 send_sample.py --url https://xxxx-xxxx.ngrok-free.app/ --payload samples/challenge_payload.json
```

> **NOTE:**
> - ngrok の無料プランでは起動のたびに URL が変わります。URL を変えたら MiiTel Admin の設定も更新してください。
> - `https://` の URL を使ってください。
> - ngrok の Web インスペクタ（既定 http://127.0.0.1:4040）で、MiiTel から届いた
>   生のリクエスト/レスポンスを確認でき、Challenge-Response のデバッグに便利です。

### 4. MiiTel Admin に登録する

1. https://account.miitel.jp/v1/signin に管理者権限でログイン → MiiTel Admin
2. [外部連携] > [Outgoing Webhook] を開く
   - **通話履歴**: そのまま [通話履歴連携設定を追加]
   - **会議履歴**: [会議履歴] タブ > [連携設定を追加]
3. **URL** に本サーバーの公開 URL を設定（ローカル検証時は上記 ngrok の転送先 URL）
4. 必要に応じて **追加ヘッダー**（例 `{"Authorization":"Bearer ACCESSTOKEN"}`）を設定し、
   サーバー側は `--auth-value "Bearer ACCESSTOKEN"` で一致させる
5. **通知ルール**を選び [保存] → このとき Challenge-Response が実行されます
   - 会議履歴は「文字起こし完了時」「議事録作成完了時」から最低 1 つを選択（両方可）

> **NOTE:**
> - `User-Agent` と `Content-Type` は MiiTel 側で固定のため、追加ヘッダーで指定しても反映されません。
> - 追加ヘッダーの JSON はシングルクォート (`'`) ではなく**ダブルクォート (`"`)** で記述してください。
> - Challenge-Response が成立しないと設定を保存できません。
> - 本サーバーは 1 つの URL で通話履歴・会議履歴の両方を受信できます（ボディの `call` / `video` で自動判別）。

## ファイル構成

```
outgoing-webhook/python/
├── README.md                # このファイル
├── server.py                # 受信サーバー (http.server)
├── miitel_outgoing.py       # 検証・要約・重複排除・保存のヘルパー
├── send_sample.py           # ローカル動作確認用の送信クライアント
└── samples/
    ├── challenge_payload.json            # Challenge-Response 確認用
    ├── transcription_payload.json        # 通話履歴: 文字起こし終了時
    ├── video_transcription_payload.json  # 会議履歴: 文字起こし完了時
    └── video_summary_payload.json        # 会議履歴: 議事録作成完了時
```

## 補足（正直ベース）

- レスポンスの方針: 正常受信・challenge は `200`、本文が不正（Content-Length / JSON）なら `400`、
  受信後の処理（保存・重複排除など）で想定外の例外が出た場合は `500` を返します。`500`/無応答は
  MiiTel 側の再送対象になるため、取りこぼしを避けられます。重い処理はキュー投入などで非同期化し、
  受信ハンドラは速やかに返すのが安全です。
- 受信内容は `miitel_outgoing.summarize()` で要約表示します（通話履歴 `call` / 会議履歴 `video` 自動判別）。
  業務で使うフィールドに合わせて適宜拡張してください。
- 本番運用では `print` ではなく Python の `logging` モジュールでの記録を推奨します。
- タイムスタンプは ISO 8601・UTC（`+00:00`）です。パースは `datetime.fromisoformat()` が利用できます。
- `speech_recognition.summary`（要約文）は 2025-06-19 以降、非表示（空文字列 `""`）です。
  会議履歴の AI 要約は「議事録作成完了時」に別階層の `summary`（`template_type` / `raw`）で届きます。
