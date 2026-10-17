"""Turn a buy/sell/watch instruction into sheet edits (computed here, written by the Apps Script)."""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Plan:
    summary: str
    ops: list[dict] = field(default_factory=list)


def plan_trade(positions: pd.DataFrame, action: str, ticker: str, price: float,
               amount_usd: float = 0.0, fraction: float = 0.0, date: str | None = None,
               note: str = "", price_estimated: bool = False) -> Plan:
    """positions: output of portfolio.value() (needs ticker, amount_usd, entry_used, entry_date, note)."""
    ticker = ticker.upper().strip()
    date = date or dt.date.today().isoformat()
    est = " (체결가 추정: 현재가)" if price_estimated else ""
    row = positions[positions["ticker"] == ticker]
    cur = row.iloc[0] if not row.empty else None

    if action == "buy":
        if amount_usd <= 0:
            raise ValueError("매수 금액(달러)이 필요합니다.")
        if cur is not None:
            old_amt, old_px = float(cur["amount_usd"]), float(cur["entry_used"])
            shares = old_amt / old_px + amount_usd / price
            new_amt = old_amt + amount_usd
            new_px = new_amt / shares
            entry_date = cur["entry_date"].date().isoformat() if pd.notna(cur["entry_date"]) else date
            summary = (f"{ticker} 추가 매수 ${amount_usd:,.0f} @ {price:,.2f}{est} → 보유 ${new_amt:,.0f}, "
                       f"평균 단가 {old_px:,.2f} → {new_px:,.2f}")
        else:
            new_amt, new_px, entry_date = amount_usd, price, date
            summary = f"{ticker} 신규 매수 ${amount_usd:,.0f} @ {price:,.2f}{est}"
        if new_amt > 200_000:
            summary += f" ⚠️ 1M 대비 {new_amt / 10_000:.1f}%로 20% 상한을 넘습니다"
        ops = [{"op": "upsert_position", "ticker": ticker, "amount_usd": round(new_amt, 2),
                "entry_price": round(new_px, 4), "entry_date": entry_date,
                "note": note or (cur["note"] if cur is not None and isinstance(cur.get("note"), str) else "")},
               {"op": "append_trade", "date": date, "action": "buy", "ticker": ticker,
                "amount_usd": round(amount_usd, 2), "price": price, "realized_pnl": 0, "note": note}]
        return Plan(summary, ops)

    if action == "sell":
        if cur is None:
            raise ValueError(f"{ticker}는 보유 종목이 아닙니다.")
        old_amt, old_px = float(cur["amount_usd"]), float(cur["entry_used"])
        shares = old_amt / old_px
        if fraction > 0:
            sell_shares = shares * min(fraction, 1.0)
        elif amount_usd > 0:
            sell_shares = min(amount_usd / price, shares)
        else:
            sell_shares = shares  # 수량을 말하지 않으면 전량
        proceeds = sell_shares * price
        realized = sell_shares * (price - old_px)
        left = shares - sell_shares
        full = left * old_px < 1  # $1 미만 남으면 전량 매도로 본다
        kind = "전량" if full else f"{sell_shares / shares:.0%}"
        summary = (f"{ticker} {kind} 매도 ${proceeds:,.0f} @ {price:,.2f}{est}, "
                   f"실현 손익 {'+' if realized >= 0 else '−'}${abs(realized):,.0f}")
        ops = [{"op": "delete_position", "ticker": ticker} if full else
               {"op": "upsert_position", "ticker": ticker, "amount_usd": round(left * old_px, 2),
                "entry_price": round(old_px, 4),
                "entry_date": cur["entry_date"].date().isoformat() if pd.notna(cur["entry_date"]) else date,
                "note": cur["note"] if isinstance(cur.get("note"), str) else ""},
               {"op": "append_trade", "date": date, "action": "sell", "ticker": ticker,
                "amount_usd": round(proceeds, 2), "price": price, "realized_pnl": round(realized, 2), "note": note}]
        return Plan(summary, ops)

    raise ValueError(f"알 수 없는 거래: {action}")


def plan_watch(current: list[str], ticker: str, add: bool) -> Plan:
    ticker = ticker.upper().strip()
    new = [t for t in current if t != ticker] + ([ticker] if add else [])
    return Plan(f"{ticker} 레이더 관심 종목 {'추가' if add else '제외'}", [{"op": "set_watch", "tickers": new}])


def send(url: str, token: str, ops: list[dict]) -> dict:
    data = json.dumps({"token": token, "ops": ops}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:  # Apps Script answers after a redirect; urllib follows it
        return json.loads(r.read().decode())


# ---------- Bloomberg 포트 현황 붙여넣기 ----------
_SECTION = re.compile(r"\[(보유 중|체결 대기|청산 완료)\]")
_BBG = r"([A-Z0-9]{1,6}(?:/[A-Z])? (?:US|UN|UW|UQ|TT|NA|LN|GY|GR|FP|JP|JT|HK|KS|CN|AU|SW|IM|SM))"


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("+", ""))


def parse_snapshot(text: str) -> dict:
    """'[보유 중] TWLO US 138,524 / P&L -11,454 (-7.62%) ...' 형식의 블룸버그 현황 텍스트를 읽는다."""
    parts = _SECTION.split(text)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    held: dict[str, dict] = {}
    for m in re.finditer(_BBG + r"\s+([\d,]+)\s*/\s*P&L\s*([+\-]?[\d,]+)", sections.get("보유 중", "")):
        h = held.setdefault(m.group(1), {"value": 0.0, "pnl": 0.0})  # 같은 종목이 두 줄이면 합친다
        h["value"] += _num(m.group(2))
        h["pnl"] += _num(m.group(3))
    closed = {m.group(1): _num(m.group(2))
              for m in re.finditer(_BBG + r"\s+P&L\s*([+\-]?[\d,]+)", sections.get("청산 완료", ""))}
    pending = {m.group(1): _num(m.group(2))
               for m in re.finditer(_BBG + r"\s+([\d,]+)", sections.get("체결 대기", ""))}
    head = {k: _num(v) for k, v in re.findall(r"(Rel P&L|P&L)\s*([+\-]?[\d,]+)", text.split("[")[0])}
    return {"held": held, "closed": closed, "pending": pending, "header": head}


def plan_snapshot(text: str, current: pd.DataFrame, logged_closed: set[str], to_yahoo,
                  price_now, date: str | None = None) -> Plan:
    """Sheet edits that make the positions tab match the pasted snapshot.

    current: positions tab (ticker column). logged_closed: tickers whose sale is already in trades.
    to_yahoo(bbg)->str|None, price_now(yahoo)->float|None.
    """
    snap = parse_snapshot(text)
    if not snap["held"]:
        raise ValueError("보유 종목을 읽지 못했습니다. '[보유 중] TWLO US 138,524 / P&L -11,454' 형식인지 확인하세요.")
    date = date or dt.date.today().isoformat()
    ops, lines, keep = [], [], set()
    for bbg, h in snap["held"].items():
        t = to_yahoo(bbg)
        if not t:
            raise ValueError(f"{bbg}를 Yahoo 티커로 바꾸지 못했습니다.")
        keep.add(t)
        cost = h["value"] - h["pnl"]  # 들어간 돈 = 평가액 − 손익
        px = price_now(t)
        entry = px * cost / h["value"] if px else None  # 지금 가격에서 수익률만큼 거꾸로 계산한 평균 단가
        ops.append({"op": "upsert_position", "ticker": t, "amount_usd": round(cost, 2),
                    "entry_price": round(entry, 4) if entry else "", "entry_date": date,
                    "note": f"블룸버그 현황 {date} (평가 ${h['value']:,.0f}, P&L {h['pnl']:+,.0f})"})
        lines.append(f"{t} 투자금 ${cost:,.0f} (평가 ${h['value']:,.0f}, P&L {h['pnl']:+,.0f})")
    gone = [t for t in current["ticker"] if t not in keep]
    ops += [{"op": "delete_position", "ticker": t} for t in gone]
    for bbg, pnl in snap["closed"].items():
        t = to_yahoo(bbg) or bbg
        if t in logged_closed:
            continue  # 이미 거래 일지에 있는 청산은 두 번 넣지 않는다
        ops.append({"op": "append_trade", "date": date, "action": "sell", "ticker": t, "amount_usd": "",
                    "price": "", "realized_pnl": pnl, "note": "블룸버그 현황에서 가져온 청산"})
    head = snap["header"]
    if "P&L" in head and "Rel P&L" in head:  # 순위 기준 숫자를 시트에 남겨 포트폴리오 탭에서 보여 준다
        ops.append({"op": "append_snapshot", "date": date, "pnl": head["P&L"], "rel_pnl": head["Rel P&L"]})
    summary = [f"보유 {len(keep)}종목으로 맞춤: " + " / ".join(lines)]
    if gone:
        summary.append("시트에서 뺄 종목: " + ", ".join(gone))
    new_closed = {b: p for b, p in snap["closed"].items() if (to_yahoo(b) or b) not in logged_closed}
    if new_closed:
        summary.append("실현 손익 기록: " + ", ".join(f"{b} {p:+,.0f}" for b, p in new_closed.items())
                       + f" (합계 {sum(new_closed.values()):+,.0f})")
    if snap["pending"]:
        summary.append("체결 대기(시트에는 아직 안 넣음): " + ", ".join(f"{b} ${v:,.0f}" for b, v in snap["pending"].items()))
    return Plan("\n".join(summary), ops)
