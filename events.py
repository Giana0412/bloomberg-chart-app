"""Earnings dates and option-implied moves (Yahoo Finance)."""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import yfinance as yf

CHALLENGE_END = dt.date(2026, 11, 13)


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
