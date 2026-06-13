# miitel-integration-examples

MiiTel の Incoming Webhook / Outgoing Webhook / ThirdParty 系拡張機能の
サンプルコード集です。

## サンプル一覧

### Incoming Webhook

外部の通話録音・会議録画を MiiTel に取り込む Webhook のサンプルです。

- [Python](./incoming-webhook/python/) — MiiTel Phone (MP) / MiiTel Meetings (MM) 両対応。標準ライブラリのみ。

### Outgoing Webhook

MiiTel が送信する通話履歴などを受信する Webhook サーバーのサンプルです。

- [Python](./outgoing-webhook/python/) — 通話履歴の受信（Challenge-Response / 重複排除対応）。標準ライブラリのみ。

## 参考

- [MiiTel Developers](https://developers.miitel.com/)
