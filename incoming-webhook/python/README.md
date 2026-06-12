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
- MM: [Video Incoming Webhook の仕様と利用方法](https://developers.miitel.com/docs/video-incoming-webhook-getting-started) / [API リファレンス](https://developers.miitel.com/reference/video__webhook_video_reception)

## 事前準備（MP）

1. Incoming Webhook の契約を **MiiTel 担当者 / サポート**に依頼します（管理者権限が必要）。
2. MiiTel Admin の **[外部連携] > [Incoming Webhook] > [URL を作成]** で **Webhook URL** を発行します。
   - 1 つの企業 ID につき作成できる URL は 1 つです。
3. 応対ユーザーに **[ユーザー設定] > 編集 > 「Incoming Webhook の利用」を許可**し、
   **[ユーザー ID を確認]** で UUID をコピーします。
   - この UUID をメタデータの `participants[].miitel_user_id` に指定します。

> **MP の Webhook POST に認証ヘッダーは不要です。** 公式チュートリアルも `Content-Type`
> のみで送信しており、**発行された Webhook URL 自体が資格情報**です。
> （`authenticate.py` は MiiTel Open API 全般向けのトークン取得用に同梱していますが、
> Incoming Webhook の送信には使いません。下記「補足: アクセストークン」を参照。）

### 環境変数

```bash
# MiiTel Phone 用（トークンは不要）
export MIITEL_IW_WEBHOOK_URL="https://（Admin で発行した Webhook URL）"
export MIITEL_USER_ID="{取得したユーザーID}"

# MiiTel Meetings / Video 用
export MIITEL_VIDEO_IW_WEBHOOK_URL="https://（発行された Webhook URL）"
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
    --audio call_data=./samples/sample.mp3 \
    --miitel-user-id "$MIITEL_USER_ID" \
    --dry-run

# 実際に送信（メタデータ POST → 音声 PUT）
python3 phone_incoming_webhook.py \
    --webhook-url "$MIITEL_IW_WEBHOOK_URL" \
    --metadata samples/phone_call_data.json \
    --audio call_data=./samples/sample.mp3 \
    --miitel-user-id "$MIITEL_USER_ID"
```

- `--audio call_data_id=PATH` は複数指定できます（call_data ごとに音声を対応付け）。
- `--webhook-url` は環境変数 `MIITEL_IW_WEBHOOK_URL` を設定していれば省略可能です。
- `--miitel-user-id`（環境変数 `MIITEL_USER_ID`）を指定すると、JSON を手編集せずに
  [ユーザー ID を確認] でコピーした UUID を差し込めます。**metadata 内の `null` でない
  `miitel_user_id` をすべて上書き**し、取引先側など `null` の participant はそのままです
  （= 応対ユーザーの participant に非 `null` のプレースホルダを置いておく運用）。
- MP では認証トークンは不要ですが、必要な場合のみ `--token`（環境変数 `MIITEL_IW_TOKEN`）を指定できます。

#### 主なメタデータ項目（`call_data[]`）

| フィールド | 必須 | 説明 |
| --- | :---: | --- |
| `call_data_id` | ✓ | 通話を識別する任意の一意 ID（音声アップロードの紐付けに使用） |
| `audio_file_type` | ✓ | `mp3` / `m4a` / `wav` |
| `event_type` | ✓ | `EXTENSION` / `OUTGOING_CALL` / `INCOMING_CALL` / `AUTOMATIC_TRANSFER` / `AUTOMATIC_RECORD` / `EXTENSION_TRANSFER` / `OUTGOING_TRANSFER` |
| `call_starts_at` / `call_answered_at` / `call_ends_at` | ✓ | ISO 8601 形式の時刻（`call_answered_at` は null 可） |
| `audio_channel_type` | ✓ | `STEREO` / `MONAURAL` |
| `participants[]` | ✓ | `type`(`FROM`/`TO`), `stereo_lr`(`left`/`right`), `miitel_user_id`, `number`, `name` |
| `group_name` / `queue_name` | | 任意（null 可） |
| `circuit_number` | | 回線番号（`^[+*#0-9][0-9]*$`、null 可） |
| `tags[]` | | `{"value": "..."}`（1〜512 文字） |

> `miitel_user_id` は `event_type` と参加者の `type` の組み合わせで必須になります。
> 例: `OUTGOING_CALL`/`OUTGOING_TRANSFER` は `FROM` 側で必須、`INCOMING_CALL` は
> `call_answered_at` が null でなければ `TO` 側で必須、など。詳細は公式ドキュメントを参照。
>
> JSON Schema: <https://github.com/revcomm/miitel-developers-public/blob/main/schema/incoming_webhook/schema.json>

> **音声アップロード URL の有効期限は発行から 3 時間**です（期限切れ・誤った URL は
> PUT 時に 403）。POST 後は速やかに PUT してください。

### MiiTel Meetings / Video (MM)

MM 用の Webhook URL は MiiTel Admin の **[外部連携] > [Incoming Webhook] > [会議履歴] タブ
> [URL を作成]** で発行します。応対ユーザーには **「Incoming Webhook（会議履歴）を使用する」**
を許可し、その **ユーザー ID（UUID）** を `video_data.host` / `participants[].miitel_user_id`
に指定します。MP 同様、**Webhook POST に認証ヘッダーは不要**です（URL 自体が資格情報）。

参考: [仕様](https://developers.miitel.com/docs/video-incoming-webhook-getting-started) / [API リファレンス](https://developers.miitel.com/reference/video__webhook_video_reception)

```bash
cd incoming-webhook/python

# 送信内容の確認
python3 video_incoming_webhook.py \
    --metadata samples/video_data.json \
    --media ./samples/sample.mp4 \
    --miitel-user-id "$MIITEL_USER_ID" \
    --dry-run

# 実際に送信（メタデータ POST → 動画 PUT）
python3 video_incoming_webhook.py \
    --webhook-url "$MIITEL_VIDEO_IW_WEBHOOK_URL" \
    --metadata samples/video_data.json \
    --media ./samples/sample.mp4 \
    --miitel-user-id "$MIITEL_USER_ID"
```

- `--miitel-user-id`（環境変数 `MIITEL_USER_ID`）を指定すると、JSON を手編集せずに
  **`video_data.host` と `null` でない `participants[].miitel_user_id` をすべて上書き**します。
  サンプルの `host` はテナント外の UUID なので、テスト時は自分の UUID で差し替えてください。
- レスポンス内のアップロード URL は自動探索しますが、見つからない場合は
  `--upload-url-json-path data.upload_url` のようにドット区切りで明示できます。

#### メタデータ項目（`video_data` ※オブジェクト。MP の配列とは異なる）

| フィールド | 必須 | 説明 |
| --- | :---: | --- |
| `title` | ✓ | 会議タイトル |
| `file_type` | ✓ | ファイル形式（例: `mp3` / `mp4`） |
| `host` | ✓ | ホストユーザーの UUID |
| `starts_at` / `ends_at` | ✓ | ISO 8601 形式の時刻 |
| `external_id` | ✓ | 外部システム側の会議 ID |
| `number_of_participants` | ✓ | 参加者数（整数） |
| `channel_type` | ✓ | `STEREO` / `MONAURAL`（モノラルはアップロード後に話者判定） |
| `tags[]` | ✓ | `{"value": "..."}` |
| `participants[]` | ✓ | `name`, `miitel_user_id`(UUID), `stereo_lr`(`left`/`right`) |
| `metadata` | | 任意のオブジェクト（例: `{"recording_device": "iPhone"}`） |

## ファイル構成

```
incoming-webhook/python/
├── README.md                    # このファイル
├── miitel_common.py             # 共通 HTTP ヘルパー (urllib ラッパー / 認証 / リトライ)
├── authenticate.py              # アクセストークン取得 CLI
├── phone_incoming_webhook.py    # MiiTel Phone (MP) クライアント
├── video_incoming_webhook.py    # MiiTel Meetings / Video (MM) クライアント
└── samples/
    ├── auth_credentials.json         # 認証ボディのサンプル (USER_PASSWORD)
    ├── auth_credentials_refresh.json # 認証ボディのサンプル (REFRESH_TOKEN)
    ├── phone_call_data.json          # MP メタデータのサンプル
    └── video_data.json               # MM メタデータのサンプル
```

## 補足: アクセストークン（MiiTel Open API 全般向け）

Incoming Webhook の送信自体には不要ですが、他の MiiTel Open API を呼ぶ際の
アクセストークンは **MiiTel Account の認証エンドポイント**から取得します。

```
POST https://account.miitel.com/auth/v1/authenticate
```

参考: [認証 API リファレンス](https://developers.miitel.com/reference/auth__authentication)

ボディは認証フロー `flow` と `params` で構成します。

- `flow: "USER_PASSWORD"` … `params` に `email`（ログイン ID）と `password`
- `flow: "REFRESH_TOKEN"` … `params` に `refresh_token`
- `params.client_id` は省略可能

`authenticate.py` で取得できます（`--base-url` 既定値は `https://account.miitel.com`）。

```bash
python3 authenticate.py --credentials samples/auth_credentials.json
# REFRESH_TOKEN フロー: --credentials samples/auth_credentials_refresh.json
```

## その他

- ネットワークエラーや 5xx 応答時は指数バックオフ（2s, 4s, 8s）で最大 3 回リトライします。
  4xx はリクエスト内容の問題のためリトライしません。
- 音声/動画アップロードの PUT 時の `Content-Type` は、(1) `--content-type` 指定、
  (2) 署名付き URL の `content-type` クエリパラメータ、(3) ファイル拡張子からの推定、
  の優先順で決定します（S3 v2 署名の URL は Content-Type を署名に含むため、URL の指定に合わせます）。
- `miitel_common.post_json()` は Bearer / BASIC 認証の両方に対応しています。
