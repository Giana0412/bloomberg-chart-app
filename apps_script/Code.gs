/**
 * 팀 포트폴리오 시트 쓰기용 웹 앱 (Bloomberg Trading Challenge 차트 도구).
 *
 * 설치: 포트폴리오 시트 → 확장 프로그램 → Apps Script → 이 코드를 붙여넣기
 *       → 프로젝트 설정 → 스크립트 속성에 TOKEN = (아무 긴 비밀 문자열) 추가
 *       → 배포 → 새 배포 → 유형: 웹 앱, 실행: 나, 액세스: 모든 사용자 → 배포
 *       → 나온 웹 앱 URL과 TOKEN을 Streamlit Secrets에 SHEET_WRITE_URL / SHEET_WRITE_TOKEN 으로 넣기
 *
 * 앱(app)이 계산을 끝낸 결과만 보내므로 이 스크립트는 받은 대로 적기만 한다.
 * 받는 형식: {token, ops: [{op: "upsert_position"|"delete_position"|"append_trade"|"set_watch", ...}]}
 */

const POSITION_HEADER = ["ticker", "amount_usd", "entry_price", "entry_date", "note"];
const TRADE_HEADER = ["date", "action", "ticker", "amount_usd", "price", "realized_pnl", "note"];

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const body = JSON.parse(e.postData.contents);
    const token = PropertiesService.getScriptProperties().getProperty("TOKEN");
    if (!token || body.token !== token) return json_({ ok: false, error: "bad token" });
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const done = [];
    (body.ops || []).forEach(function (op) {
      if (op.op === "upsert_position") upsertPosition_(ss, op);
      else if (op.op === "delete_position") deletePosition_(ss, op.ticker);
      else if (op.op === "append_trade") appendTrade_(ss, op);
      else if (op.op === "set_watch") setWatch_(ss, op.tickers || []);
      else throw new Error("unknown op: " + op.op);
      done.push(op.op + (op.ticker ? ":" + op.ticker : ""));
    });
    return json_({ ok: true, done: done });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

function positions_(ss) {
  return ss.getSheets()[0];  // 첫 번째 탭이 보유 종목
}

function sheet_(ss, name, header) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(header);
  }
  return sh;
}

function findRow_(sh, ticker) {
  const values = sh.getDataRange().getValues();
  for (let i = 1; i < values.length; i++) {
    if (String(values[i][0]).trim().toUpperCase() === ticker) return i + 1;
  }
  return -1;
}

function upsertPosition_(ss, op) {
  const sh = positions_(ss);
  const row = [op.ticker, op.amount_usd, op.entry_price, op.entry_date, op.note || ""];
  const r = findRow_(sh, op.ticker);
  if (r > 0) sh.getRange(r, 1, 1, row.length).setValues([row]);
  else sh.appendRow(row);
}

function deletePosition_(ss, ticker) {
  const sh = positions_(ss);
  const r = findRow_(sh, ticker);
  if (r > 0) sh.deleteRow(r);
}

function appendTrade_(ss, op) {
  sheet_(ss, "trades", TRADE_HEADER).appendRow(
    [op.date, op.action, op.ticker, op.amount_usd, op.price, op.realized_pnl || 0, op.note || ""]);
}

function setWatch_(ss, tickers) {
  const sh = sheet_(ss, "watch", ["ticker"]);
  sh.clearContents();
  sh.appendRow(["ticker"]);
  tickers.forEach(function (t) { sh.appendRow([t]); });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
