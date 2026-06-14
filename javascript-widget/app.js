// MiiTel JavaScript ウィジェット サンプルのデモ用ロジック。
//
// ウィジェット本体 (v1.js) は index.html の <script async> で非同期に読み込まれる。
// 読み込み前でも miitelWidget(k, v) はスタブが conf に積むだけなので、
// イベントコールバックの登録や設定は読み込み前に呼んでも問題ない。
// 一方 miitelWidget.call() / miitelWidget.hangup() は本体読み込み後に有効になる。

(function () {
  "use strict";

  var logEl = document.getElementById("log");

  function log(message, detail) {
    var time = new Date().toLocaleTimeString();
    var line = "[" + time + "] " + message;
    if (detail !== undefined) {
      line += " " + JSON.stringify(detail);
    }
    logEl.textContent += line + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  }

  // --- イベントコールバックの登録 ---------------------------------------
  // いずれも miitelWidget("<イベント名>", コールバック) で登録する。

  miitelWidget("onReceiveCall", function (e) {
    // 着信時。内線/転送/グループ宛/ユーザー宛で内容が変わる。
    var kind;
    if (e.isInternal && !e.isTransfer) {
      kind = "内線着信 (" + e.phoneNumber + " → " + e.userName + ")";
    } else if (e.isTransfer) {
      kind = "内線転送 (" + e.phoneNumber + " / 転送元 " + e.remotePhoneNumber + ")";
    } else if (e.groupName) {
      kind = "グループ宛外線 (" + e.phoneNumber + " → " + e.circuitNumber + " / " + e.groupName + ")";
    } else {
      kind = "ユーザー宛外線 (" + e.phoneNumber + " → " + e.circuitNumber + ")";
    }
    log("onReceiveCall: " + kind, e);
  });

  miitelWidget("onChangeReadyState", function (e) {
    // 発信可否の変化。発信不可のときはクリック to コールを無効化するなどに使える。
    log("onChangeReadyState: state=" + e.state);
    var callBtn = document.getElementById("callBtn");
    if (callBtn) {
      callBtn.disabled = !e.state;
    }
  });

  miitelWidget("onReceiveSequenceId", function (e) {
    // 応対を識別するシーケンス ID。通話履歴 URL の末尾に使える。
    log("onReceiveSequenceId: " + e.sequenceId);
  });

  miitelWidget("onDialBegin", function () {
    log("onDialBegin: ダイヤル開始");
  });

  miitelWidget("onCallBegin", function () {
    log("onCallBegin: 通話開始");
  });

  miitelWidget("onCallEnd", function () {
    log("onCallEnd: 通話終了");
  });

  // --- 外観カスタマイズ (必要に応じて有効化) ----------------------------
  // miitelWidget("position", "right_bottom"); // left_bottom / right_bottom
  // miitelWidget("color", "black");            // white / black
  // miitelWidget("openButtonImage", "https://example.com/button.svg");
  // miitelWidget("logoImage", "https://example.com/logo.svg");

  // --- UI 配線 ----------------------------------------------------------

  // call()/hangup() は本体読み込み後のみ有効。未読込ならユーザーに知らせる。
  function widgetReady() {
    return typeof miitelWidget.call === "function";
  }

  function onCallClick() {
    if (!widgetReady()) {
      log("ウィジェット未読込: company_id / access_key / src を設定し、少し待ってから再度お試しください");
      return;
    }
    var phoneNumber = document.getElementById("phoneNumber").value.trim();
    if (!phoneNumber) {
      log("発信先電話番号を入力してください");
      return;
    }
    var companyName = document.getElementById("companyName").value.trim();
    var contactPersonName = document.getElementById("contactPersonName").value.trim();

    // 会社名・担当者名の両方があれば連絡先登録付きで発信。
    if (companyName && contactPersonName) {
      miitelWidget.call(phoneNumber, {
        contact: { companyName: companyName, contactPersonName: contactPersonName }
      });
      log("call: " + phoneNumber + " (連絡先登録: " + companyName + " / " + contactPersonName + ")");
    } else {
      miitelWidget.call(phoneNumber);
      log("call: " + phoneNumber);
    }
  }

  function onHangupClick() {
    if (!widgetReady()) {
      log("ウィジェット未読込のため hangup できません");
      return;
    }
    miitelWidget.hangup();
    log("hangup: 発信/着信/通話を終了");
  }

  function onCustomizeClick(ev) {
    var cmd = ev.currentTarget.getAttribute("data-cmd");
    var val = ev.currentTarget.getAttribute("data-val");
    miitelWidget(cmd, val);
    log("customize: " + cmd + " = " + val + " (反映はソフトフォンを開き直した時。color の既定は black)");
  }

  document.getElementById("callBtn").addEventListener("click", onCallClick);
  document.getElementById("hangupBtn").addEventListener("click", onHangupClick);
  document.getElementById("clearLogBtn").addEventListener("click", function () {
    logEl.textContent = "";
  });
  var customizeButtons = document.querySelectorAll("button[data-cmd]");
  for (var i = 0; i < customizeButtons.length; i++) {
    customizeButtons[i].addEventListener("click", onCustomizeClick);
  }

  log("サンプル読み込み完了。右下のボタンが出ない場合は company_id / access_key / src を確認してください。");
})();
