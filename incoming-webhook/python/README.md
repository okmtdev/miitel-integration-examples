# MiiTel Incoming Webhook サンプル (Python)

外部の通話録音・会議録画を MiiTel に取り込む **Incoming Webhook** の Python サンプルです。

- **MiiTel Phone (MP)** … `phone_incoming_webhook.py`
- **MiiTel Meetings / Video (MM)** … `video_incoming_webhook.py`

> **依存パッケージはありません。** Python 3.10 以降の標準ライブラリ (`urllib` 等) だけで動作します。

## Incoming Webhook の仕組み

Incoming Webhook は 2 段階のフローで動きます。

1. **メタデータの送信 (POST)**
   通話 / 会議のメタデータ（種別・電話番号・時刻など）を Webhook URL に POST すると、
   MiiTel が履歴を生成し、音声 / 動画のアップロード用 URL を返します。
2. **メディアのアップロード (PUT)**
   返ってきた URL に対して、音声 / 動画ファイルをバイナリで PUT します。

参考ドキュメント:

- MP: [Incoming Webhook の仕様と利用方法](https://developers.miitel.com/docs/incoming-webhook-getting-started) / [API リファレンス](https://developers.miitel.com/reference/call__webhook_call_creation)
- MM: [Video Incoming Webhook の仕様と利用方法](https://developers.miitel.com/docs/video-incoming-webhook-getting-started) / [API リファレンス](https://developers.miitel.com/reference/videovideoincomingwebhookreceive)

## 事前準備

1. Incoming Webhook の有効化を **MiiTel CS チーム**に依頼します。
2. 払い出された **Webhook URL** と **認証トークン**を控えます。
   （Webhook URL はテナントごとに発行されるため、本サンプルでは URL を引数 / 環境変数で渡します。）

環境変数で渡す場合:

```bash
# MiiTel Phone 用
export MIITEL_IW_WEBHOOK_URL="https://（CS から払い出された URL）"
export MIITEL_IW_TOKEN="（認証トークン）"

# MiiTel Meetings / Video 用
export MIITEL_VIDEO_IW_WEBHOOK_URL="https://（CS から払い出された URL）"
export MIITEL_VIDEO_IW_TOKEN="（認証トークン）"
```

## 使い方

### MiiTel Phone (MP)

`samples/phone_call_data.json` のようなメタデータ JSON を用意し、`call_data_id` と
音声ファイルを対応付けて実行します。

```bash
cd incoming-webhook/python

# まずは送信内容だけ確認（送信しない）
python3 phone_incoming_webhook.py \
    --metadata samples/phone_call_data.json \
    --audio test_id=./recording.mp3 \
    --dry-run

# 実際に送信（メタデータ POST → 音声 PUT）
python3 phone_incoming_webhook.py \
    --webhook-url "$MIITEL_IW_WEBHOOK_URL" \
    --token "$MIITEL_IW_TOKEN" \
    --metadata samples/phone_call_data.json \
    --audio test_id=./recording.mp3
```

- `--audio call_data_id=PATH` は複数指定できます（call_data ごとに音声を対応付け）。
- `--webhook-url` / `--token` は環境変数を設定していれば省略可能です。

#### 主なメタデータ項目（`call_data[]`）

| フィールド | 説明 |
| --- | --- |
| `call_data_id` | 通話を識別する任意の一意 ID（音声アップロードの紐付けに使用） |
| `audio_file_type` | `mp3` / `m4a` / `wav` |
| `event_type` | `OUTGOING_CALL` / `INCOMING_CALL` / `EXTENSION` ほか |
| `call_starts_at` / `call_answered_at` / `call_ends_at` | ISO 8601 形式の時刻 |
| `circuit_number` | 回線番号 |
| `audio_channel_type` | `STEREO` / `MONAURAL` |
| `participants[]` | `type`(`FROM`/`TO`), `stereo_lr`(`left`/`right`), `miitel_user_id`, `number`, `name` |

### MiiTel Meetings / Video (MM)

```bash
cd incoming-webhook/python

# 送信内容の確認
python3 video_incoming_webhook.py \
    --metadata samples/video_data.json \
    --media ./meeting.mp4 \
    --dry-run

# 実際に送信（メタデータ POST → 動画 PUT）
python3 video_incoming_webhook.py \
    --webhook-url "$MIITEL_VIDEO_IW_WEBHOOK_URL" \
    --token "$MIITEL_VIDEO_IW_TOKEN" \
    --metadata samples/video_data.json \
    --media ./meeting.mp4
```

- レスポンス内のアップロード URL は自動探索しますが、見つからない場合は
  `--upload-url-json-path data.upload_url` のようにドット区切りで明示できます。

> **注意:** `samples/video_data.json` のフィールド名はサンプルです。MM 側の正確な
> スキーマは [Video Incoming Webhook の API リファレンス](https://developers.miitel.com/reference/videovideoincomingwebhookreceive)
> を確認のうえ調整してください。本スクリプトは JSON ファイルの内容をそのまま送信するため、
> コードを変更せずにメタデータを差し替えられます。

## ファイル構成

```
incoming-webhook/python/
├── README.md                    # このファイル
├── miitel_common.py             # 共通 HTTP ヘルパー (urllib ラッパー / 認証 / リトライ)
├── phone_incoming_webhook.py    # MiiTel Phone (MP) クライアント
├── video_incoming_webhook.py    # MiiTel Meetings / Video (MM) クライアント
└── samples/
    ├── phone_call_data.json     # MP メタデータのサンプル
    └── video_data.json          # MM メタデータのサンプル
```

## 補足

- ネットワークエラーや 5xx 応答時は指数バックオフ（2s, 4s, 8s）で最大 3 回リトライします。
  4xx はリクエスト内容の問題のためリトライしません。
- 認証は Bearer トークンを既定とし、`miitel_common.post_json()` は BASIC 認証にも対応しています。
- 音声 / 動画の `Content-Type` はファイル拡張子から自動判定します。
