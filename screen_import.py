"""Import a Bloomberg EQS screen export (Google Sheet / CSV / XLSX) and map tickers to Yahoo."""
from __future__ import annotations

import io

import pandas as pd
import yfinance as yf

from portfolio import sheet_csv_url

# Bloomberg exchange code -> Yahoo suffixes to try, in order
SUFFIX = {
    "US": [""], "UN": [""], "UW": [""], "UQ": [""],
    "TT": [".TW", ".TWO"], "KS": [".KS", ".KQ"], "KQ": [".KQ"],
    "JP": [".T"], "JT": [".T"], "HK": [".HK"], "C1": [".SS"], "C2": [".SZ"], "CH": [".SS", ".SZ"],
    "BZ": [".SA"], "IN": [".NS", ".BO"], "MK": [".KL"], "TI": [".IS"], "LN": [".L"],
    "GR": [".DE"], "GY": [".DE"], "FP": [".PA"], "NA": [".AS"], "SW": [".SW"], "SE": [".SW"],
    "CN": [".TO"], "CT": [".TO"], "AU": [".AX"], "AT": [".AX"], "SP": [".SI"], "IM": [".MI"],
    "SM": [".MC"], "SS": [".ST"], "DC": [".CO"], "NO": [".OL"], "FH": [".HE"], "BB": [".BR"],
}


def read_export(source: str | bytes, filename: str = "") -> pd.DataFrame:
    """Rows of the export whose first column looks like 'XXXX YY Equity'."""
    if isinstance(source, (bytes, bytearray)):
        raw = (pd.read_excel(io.BytesIO(source), header=None) if filename.lower().endswith(("xlsx", "xls"))
               else pd.read_csv(io.BytesIO(source), header=None, dtype=str))
    else:
        raw = pd.read_csv(sheet_csv_url(source), header=None, dtype=str)
    raw = raw.dropna(how="all")
    first = raw.iloc[:, 0].astype(str).str.strip()
    hdr_idx = first[first.str.lower() == "ticker"].index
    header = raw.loc[hdr_idx[0]].fillna("").astype(str).tolist() if len(hdr_idx) else ["Ticker"] + [f"col{i}" for i in range(1, raw.shape[1])]
    rows = raw[first.str.endswith(" Equity")].copy()
    rows.columns = [h.strip() or f"col{i}" for i, h in enumerate(header)]
    return rows.reset_index(drop=True)


def candidates(bbg: str) -> list[str]:
    parts = bbg.replace(" Equity", "").split()
    if len(parts) < 2:
        return []
    sym, exch = " ".join(parts[:-1]), parts[-1].upper()
    if exch == "HK" and sym.isdigit():
        sym = sym.zfill(4)
    if exch in ("US", "UN", "UW", "UQ"):
        sym = sym.replace("/", "-")
    return [sym + s for s in SUFFIX.get(exch, [])]


def map_tickers(bbg_tickers: list[str]) -> dict[str, str | None]:
    """Bloomberg ticker -> Yahoo ticker that actually returns prices (None if none works)."""
    tries = {b: candidates(b) for b in bbg_tickers}
    first = sorted({c[0] for c in tries.values() if c})
    ok: set[str] = set()

    def probe(symbols: list[str]) -> None:
        if not symbols:
            return
        df = yf.download(symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False)
        for s in symbols:
            try:
                col = df[s]["Close"] if len(symbols) > 1 else df["Close"]
                if col.dropna().size:
                    ok.add(s)
            except Exception:
                pass

    probe(first)
    second = sorted({c[1] for c in tries.values() if len(c) > 1 and c[0] not in ok})
    probe(second)
    return {b: next((c for c in cs if c in ok), None) for b, cs in tries.items()}
