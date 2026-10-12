"""Team portfolio from a Google Sheet, valued against the benchmark proxy (ACWI)."""
from __future__ import annotations

import re

import pandas as pd

NOTIONAL = 1_000_000
BENCH = "ACWI"  # WLS 지수는 Yahoo에 없어서 비슷한 전 세계 지수 ETF로 대신함
CAP = 20.0  # 단일 종목 상한 (% of notional)


def sheet_csv_url(url_or_id: str) -> str:
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url_or_id)
    sid = m.group(1) if m else url_or_id.strip()
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"


def read_positions(url_or_id: str) -> pd.DataFrame:
    df = pd.read_csv(sheet_csv_url(url_or_id))
    df.columns = [c.strip().lower() for c in df.columns]
    need = {"ticker", "amount_usd", "entry_date"}
    if not need <= set(df.columns):
        raise ValueError(f"시트 첫 줄에 {', '.join(sorted(need))} 열이 있어야 합니다.")
    df = df[df["ticker"].notna()].copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["amount_usd"] = pd.to_numeric(df["amount_usd"].astype(str).str.replace(",", ""), errors="coerce")
    df["entry_price"] = pd.to_numeric(df.get("entry_price"), errors="coerce")
    df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
    return df[df["amount_usd"] > 0]


def value(positions: pd.DataFrame, closes: dict[str, pd.Series], start: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """closes: ticker -> daily close series in USD (benchmark included under BENCH)."""
    rows = []
    for _, p in positions.iterrows():
        s = closes.get(p["ticker"])
        if s is None or s.empty:
            rows.append({**p, "error": "가격 없음"})
            continue
        entry = p["entry_price"]
        if pd.isna(entry):
            after = s[s.index >= p["entry_date"]] if pd.notna(p["entry_date"]) else s
            entry = float(after.iloc[0]) if not after.empty else float(s.iloc[-1])
        last = float(s.iloc[-1])
        shares = p["amount_usd"] / entry
        val = shares * last
        rows.append({**p, "entry_used": entry, "last": last, "value": val,
                     "pnl": val - p["amount_usd"], "ret": (last / entry - 1) * 100})
    df = pd.DataFrame(rows)
    invested = float(df["amount_usd"].sum())
    mkt = float(df["value"].sum()) if "value" in df else 0.0
    cash = NOTIONAL - invested
    total = mkt + cash
    df["weight_now"] = df.get("value", 0) / total * 100
    df["cap_room"] = CAP - df.get("value", 0) / NOTIONAL * 100

    b = closes.get(BENCH)
    bench_ret = None
    if b is not None and not b.empty:
        bs = b[b.index >= start]
        if not bs.empty:
            bench_ret = (float(b.iloc[-1]) / float(bs.iloc[0]) - 1) * 100
    port_ret = (total / NOTIONAL - 1) * 100
    summary = {"invested": invested, "cash": cash, "total": total, "port_ret": port_ret,
               "bench_ret": bench_ret, "rel": None if bench_ret is None else port_ret - bench_ret,
               "rel_usd": None if bench_ret is None else total - NOTIONAL * (1 + bench_ret / 100)}
    return df, summary
