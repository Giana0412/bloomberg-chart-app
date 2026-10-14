"""Turn a buy/sell/watch instruction into sheet edits (computed here, written by the Apps Script)."""
from __future__ import annotations

import datetime as dt
import json
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
