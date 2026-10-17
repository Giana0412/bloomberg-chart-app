"""Team portfolio from a Google Sheet, valued against the benchmark proxy (ACWI)."""
from __future__ import annotations

import re

import pandas as pd

NOTIONAL = 1_000_000
BENCH = "ACWI"  # WLS 지수는 Yahoo에 없어서 비슷한 전 세계 지수 ETF로 대신함
CAP = 20.0  # 단일 종목 상한 (% of notional)


def sheet_id(url_or_id: str) -> str:
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def sheet_csv_url(url_or_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id(url_or_id)}/export?format=csv"


def _tab(url_or_id: str, name: str, need: set[str]) -> pd.DataFrame:
    """A named tab (e.g. trades, watch). Empty if missing — gviz falls back to the first tab, so check columns."""
    try:
        df = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{sheet_id(url_or_id)}/gviz/tq?tqx=out:csv&sheet={name}")
    except Exception:
        return pd.DataFrame(columns=sorted(need))
    df.columns = [str(c).strip().lower() for c in df.columns]
    is_positions_tab = {"amount_usd", "entry_date"} <= set(df.columns)  # gviz가 탭이 없어서 첫 탭을 돌려준 경우
    return df if need <= set(df.columns) and not is_positions_tab else pd.DataFrame(columns=sorted(need))


def read_trades(url_or_id: str) -> pd.DataFrame:
    df = _tab(url_or_id, "trades", {"date", "action", "ticker", "realized_pnl"})
    if not df.empty:
        df["realized_pnl"] = pd.to_numeric(df["realized_pnl"], errors="coerce").fillna(0)
    return df


def read_snapshots(url_or_id: str) -> pd.DataFrame:
    """블룸버그 현황을 붙여넣을 때 남긴 공식 P&L / Rel P&L 기록 (오래된 순)."""
    df = _tab(url_or_id, "snapshots", {"date", "pnl", "rel_pnl"})
    for c in ("pnl", "rel_pnl"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["pnl", "rel_pnl"])


def read_watch(url_or_id: str) -> list[str]:
    df = _tab(url_or_id, "watch", {"ticker"})
    return [str(t).strip().upper() for t in df.get("ticker", []) if str(t).strip() and str(t) != "nan"]


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


def value(positions: pd.DataFrame, closes: dict[str, pd.Series], start: pd.Timestamp,
          realized: float = 0.0) -> tuple[pd.DataFrame, dict]:
    """closes: ticker -> daily close series in USD (benchmark included under BENCH).
    realized: 매도로 확정된 손익 합계 (현금에 더해진다)."""
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
    cash = NOTIONAL - invested + realized
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
    summary = {"invested": invested, "cash": cash, "realized": realized, "total": total, "port_ret": port_ret,
               "bench_ret": bench_ret, "rel": None if bench_ret is None else port_ret - bench_ret,
               "rel_usd": None if bench_ret is None else total - NOTIONAL * (1 + bench_ret / 100)}
    return df, summary
