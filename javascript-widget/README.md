# MiiTel JavaScript ウィジェット サンプル

外部の Web アプリケーション（CRM、予約管理、発注・在庫管理など）に **MiiTel Phone（ソフトフォン）**
を埋め込むための JavaScript ウィジェットのサンプルです。

- `index.html` … ウィジェットを埋め込んだデモページ（クリック to コール・各種イベント・外観カスタマイズ）
- `app.js` … デモのロジック（イベント登録・ボタン配線）

> **ビルド不要。** 静的な HTML / JavaScript だけで動作します。

参考: [JavaScript Widget の仕様と利用方法](https://developers.miitel.com/docs/)（MiiTel Developers）

## 事前準備

1. 管理者権限で MiiTel Admin にログイン（https://account.miitel.jp/v1/signin →（左上）⋮⋮⋮ → Admin）。
2. **[外部連携] > [JavaScript ウィジェット]** を開き、表示される HTML スニペットを取得します。
   スニペットは次の形です（`company_id` / `access_key` / `src` はテナント固有）。

   ```html
   <!-- begin miitel widget -->
   <script>
     window.miitelWidget = window.miitelWidget || function (k, v) {
       miitelWidget.conf = miitelWidget.conf || {}; miitelWidget.conf[k] = v;
     };
     miitelWidget("company_id", "YOUR_COMPANY_ID");
     miitelWidget("access_key", "YOUR_ACCESS_KEY");
   </script>
   <script async src="https://api.miitel.com/static/widget/v1.js"></script>
   <!-- end miitel widget -->
   ```

3. `index.html` の `<!-- begin miitel widget -->` 〜 `<!-- end miitel widget -->` の**ブロックを丸ごと**、
   取得したスニペットで置き換えます。`company_id` / `access_key` だけでなく、
   **`src` のホストもテナント固有**（環境で異なる）なので必ず差し替えてください。

> **注意:** `access_key` はブラウザに配信される**公開クライアントキー**です（ページのソースで見えます）。
> サーバー用シークレットではありませんが、リポジトリにはテナント固有値を直書きせず
> プレースホルダのままにしています。本番では自社の値に差し替えてください。

## ローカルで動かす

`file://` でも動く場合がありますが、ウィジェットの読み込みは HTTP 経由が確実です。

```bash
cd javascript-widget
python3 -m http.server 8000
# ブラウザで http://localhost:8000/ を開く
```

スニペット（`company_id` / `access_key` / `src`）を正しく設定していれば、画面右下に
**[MiiTel Phone]** ボタンが表示されます。

### うまく表示されないとき

- **`GET https://.../static/widget/v1.js net::ERR_NAME_NOT_RESOLVED`**
  → `src` のホストがテナントと不一致です。Admin スニペットの `src` をそのまま使ってください
  （例: 開発テナントは `https://api.miiteldevelopment.net/static/widget/v1.js`）。
- **ボタンが出ない / 401・403 が出る** → `company_id` / `access_key` が未設定またはプレースホルダのままです。
- ブラウザの開発者ツール（Network / Console）でエラー内容を確認すると原因を切り分けやすいです。

## 提供 API（`window.miitelWidget`）

スニペットを読み込むと、グローバルに `miitelWidget` が定義されます。

### 発信 / 通話終了

```js
// 発信のみ
miitelWidget.call("09012345678");

// 発信＋連絡先登録（会社名・担当者名の両方が必要。片方が空だと登録されない）
miitelWidget.call("09012345678", {
  contact: { companyName: "取引先会社名", contactPersonName: "取引先担当者名" }
});

// 発信中/着信中/通話中を終了
miitelWidget.hangup();
```

- `phoneNumber` は**半角数字**で指定します。
- 連絡先が既に存在する番号の場合、会社名・担当者名は上書きされます。
- `call()` / `hangup()` は**ウィジェット本体（v1.js）の読み込み後**に有効です。本サンプルは
  `typeof miitelWidget.call === "function"` で読み込み済みかを確認しています。

### イベントコールバック

`miitelWidget("<イベント名>", callback)` で登録します（本体読み込み前に呼んでも OK）。

| イベント | 発火タイミング | 主な引数 |
| --- | --- | --- |
| `onReceiveCall` | 着信時 | `phoneNumber` / `groupName` / `circuitTitle` / `circuitNumber` / `userName` / `isInternal` / `isTransfer` / `remotePhoneNumber` |
| `onChangeReadyState` | 発信可否が変化した時 | `state`（true=発信可） |
| `onReceiveSequenceId` | シーケンス ID 受領時 | `sequenceId`（通話履歴 URL `…/app/calls/<sequenceId>` に使える） |
| `onDialBegin` | ダイヤル開始 / 着信受領時 | － |
| `onCallBegin` | 通話開始時 | － |
| `onCallEnd` | 発信 / 着信の終了時 | － |

### 外観カスタマイズ

```js
miitelWidget("position", "left_bottom"); // left_bottom / right_bottom（既定 right_bottom）
miitelWidget("color", "black");           // white / black（既定 black）
miitelWidget("openButtonImage", "https://example.com/button.svg"); // 展開ボタン画像
miitelWidget("logoImage", "https://example.com/logo.svg");          // ロゴ画像
```

- 画像は **https の SVG・180×30px 推奨**です。

## ファイル構成

```
javascript-widget/
├── README.md     # このファイル
├── index.html    # ウィジェットを埋め込んだデモページ
└── app.js        # デモのロジック（イベント登録・ボタン配線・外観切替）
```

## 注意事項

- 本機能の組み込みは **Web アプリ開発者**が行うもので、一般利用者向けではありません（設定取得には管理者権限が必要）。
- **完全な SPA でない**（ページ遷移でリロードが発生する）Web アプリに埋め込むと、
  通話中の画面遷移で**通話が切断される**可能性があります。
- ボタン/ロゴ画像の URL は `https://` で始まる必要があります。
