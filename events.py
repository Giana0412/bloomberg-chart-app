"""Earnings dates and option-implied moves (Yahoo Finance)."""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import yfinance as yf

CHALLENGE_END = dt.date(2026, 11, 13)


def earnings_calendar(start: dt.date, end: dt.date, min_cap: float = 2e9) -> pd.DataFrame:
    """All US earnings between start and end (inclusive) with market cap >= min_cap."""
    cal = yf.Calendars(start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat())
    pages, offset = [], 0
    while offset < 1000:
        page = cal.get_earnings_calendar(market_cap=min_cap, filter_most_active=False, limit=100, offset=offset)
        if page is None or page.empty:
            break
        pages.append(page)
        if len(page) < 100:
            break
        offset += 100
    if not pages:
        return pd.DataFrame(columns=["symbol", "company", "cap", "date", "timing", "eps_est"])
    df = pd.concat(pages).reset_index()
    df = df.rename(columns={"Symbol": "symbol", "Company": "company", "Marketcap": "cap",
                            "Event Start Date": "when", "Timing": "timing", "EPS Estimate": "eps_est"})
    when = pd.to_datetime(df["when"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = when.dt.date
    df = df[(df["date"] >= start) & (df["date"] <= end)].drop_duplicates("symbol")
    return df[["symbol", "company", "cap", "date", "timing", "eps_est"]].sort_values(["date", "cap"], ascending=[True, False])


def _mid(row: pd.Series) -> float | None:
    bid, ask, last = row.get("bid", 0) or 0, row.get("ask", 0) or 0, row.get("lastPrice", 0) or 0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return last if last > 0 else None


def earnings_event(ticker: str) -> dict:
    """Next earnings date plus the ATM straddle move for the first expiry on/after it.

    The straddle covers every day up to that expiry, so it slightly overstates the
    earnings-day move alone.
    """
    t = yf.Ticker(ticker)
    out: dict = {"ticker": ticker, "earnings": None, "expiry": None, "implied_move": None, "price": None}
    try:
        dates = (t.calendar or {}).get("Earnings Date") or []
        out["earnings"] = dates[0] if dates else None
    except Exception:
        pass
    try:
        out["price"] = float(t.fast_info.last_price)
    except Exception:
        return out
    try:
        expiries = list(t.options)
    except Exception:
        expiries = []
    if not expiries:
        return out
    target = out["earnings"] or dt.date.today()
    exp = next((e for e in expiries if dt.date.fromisoformat(e) >= target), None)
    if exp is None:
        return out
    try:
        ch = t.option_chain(exp)
    except Exception:
        return out
    spot = out["price"]
    calls, puts = ch.calls, ch.puts
    if calls.empty or puts.empty:
        return out
    strike = min(set(calls["strike"]) & set(puts["strike"]), key=lambda k: abs(k - spot), default=None)
    if strike is None:
        return out
    c = _mid(calls[calls["strike"] == strike].iloc[0])
    p = _mid(puts[puts["strike"] == strike].iloc[0])
    if c is None or p is None or not math.isfinite(c + p):
        return out
    out["expiry"] = exp
    out["implied_move"] = (c + p) / spot * 100
    return out


GAP_MIN = 2.0  # 팀 규칙: 다음 날 시가가 전날 종가 대비 +2% 이상
HOLD_DAYS = 5  # 통과하면 최대 5거래일 보유


def earnings_reaction(ticker: str, now: pd.Timestamp | None = None, lookback_days: int = 10) -> dict | None:
    """Team earnings rule for the most recent report in the last `lookback_days`.

    Reaction day = the first session that opens after the report time (works for pre-market,
    after-close and foreign listings alike). Pass = open ≥ prior close +2% and the price one hour
    after the open is still above the open. None if there was no recent report.
    """
    now = now or pd.Timestamp.now(tz="America/New_York")
    try:
        dates = yf.Ticker(ticker).get_earnings_dates(limit=8)
    except Exception:
        return None
    if dates is None or dates.empty:
        return None
    past = [d for d in dates.index if now - pd.Timedelta(days=lookback_days) <= d <= now]
    if not past:
        return None
    when = max(past)
    out: dict = {"ticker": ticker, "reported": when, "day": None, "verdict": "판정 대기",
                 "gap": None, "open": None, "prev_close": None, "px_1h": None, "until": None}
    bars = yf.download(ticker, period="1mo", interval="5m", progress=False, multi_level_index=False, auto_adjust=False)
    daily = yf.download(ticker, period="3mo", interval="1d", progress=False, multi_level_index=False, auto_adjust=False)
    if bars is None or bars.empty or daily is None or daily.empty:
        return out
    bars = bars.dropna(subset=["Open"])
    firsts = bars.groupby(bars.index.date).head(1)
    after = firsts[firsts.index > when]
    if after.empty:
        return out  # 아직 반응 장이 열리지 않음
    start = after.index[0]
    day = start.date()
    out["day"] = day
    prev = daily[daily.index.date < day]["Close"].dropna()
    if prev.empty:
        return out
    today_daily = daily[daily.index.date == day]
    out["open"] = float(today_daily["Open"].iloc[0]) if not today_daily.empty else float(after["Open"].iloc[0])
    out["prev_close"] = float(prev.iloc[-1])
    out["gap"] = (out["open"] / out["prev_close"] - 1) * 100
    out["until"] = pd.Timestamp(day) + pd.offsets.BDay(HOLD_DAYS)
    if out["gap"] < GAP_MIN:
        out["verdict"] = "매도"
        out["why"] = f"시가 {out['gap']:+.1f}% (기준 +{GAP_MIN:.0f}% 미달)"
        return out
    first_hour = bars[(bars.index >= start) & (bars.index < start + pd.Timedelta(minutes=60))]
    if bars.index[-1] < start + pd.Timedelta(minutes=55):
        out["why"] = f"시가 {out['gap']:+.1f}% 통과, 개장 1시간 뒤 가격 대기 중"
        return out
    out["px_1h"] = float(first_hour["Close"].iloc[-1])
    if out["px_1h"] > out["open"]:
        out["verdict"] = "보유"
        out["why"] = (f"시가 {out['gap']:+.1f}%, 1시간 뒤 {out['px_1h']:.2f} > 시가 {out['open']:.2f}. "
                      f"최대 {out['until']:%m/%d}까지 보유")
    else:
        out["verdict"] = "매도"
        out["why"] = f"시가 {out['gap']:+.1f}%였지만 1시간 뒤 {out['px_1h']:.2f} ≤ 시가 {out['open']:.2f}"
    return out
