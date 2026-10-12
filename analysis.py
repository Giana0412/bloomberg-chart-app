"""Indicator math and plain-language explanations for the chart app.

Kept free of Streamlit so it can be tested on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Analysis:
    ticker: str
    df: pd.DataFrame  # OHLCV plus indicator columns
    last: float
    prev: float
    asof: pd.Timestamp
    rsi: float
    atr: float
    stop: float
    sup: tuple[float, float] | None
    res: tuple[float, float] | None
    ma20: float | None
    ma50: float | None
    ma200: float | None
    bbu: float | None
    atr_x: float | None
    r5: float | None
    r63: float | None
    r126: float | None
    unit: str = "달러"
    signals: list[tuple[str, str]] = field(default_factory=list)  # (level, text)
    easy: str = ""
    todo: str = ""


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    c = df["Close"]
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - c.shift()).abs(), (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def sr_channels(h: np.ndarray, l: np.ndarray, prd: int = 10, width_pct: float = 5,
                max_num: int = 6, loopback: int = 290) -> list[tuple[float, float]]:
    """Simplified port of the TradingView 'Support Resistance Channels' indicator."""
    n = len(h)
    piv = []
    for i in range(max(prd, n - loopback), n - prd):
        if h[i] == h[i - prd:i + prd + 1].max():
            piv.append(h[i])
        if l[i] == l[i - prd:i + prd + 1].min():
            piv.append(l[i])
    if not piv:
        return []
    cw = (h[-300:].max() - l[-300:].min()) * width_pct / 100
    cands = []
    for p in piv:
        lo = hi = p
        cnt = 0
        for q in piv:
            if lo <= q <= hi or max(hi, q) - min(lo, q) <= cw:
                lo, hi = min(lo, q), max(hi, q)
                cnt += 1
        touch = int(((h[-loopback:] >= lo) & (l[-loopback:] <= hi)).sum())
        cands.append((cnt * 20 + touch, lo, hi))
    cands.sort(reverse=True)
    chosen: list[tuple[float, float]] = []
    for _, lo, hi in cands:
        if any(not (hi < a or lo > b) for a, b in chosen):
            continue
        chosen.append((float(lo), float(hi)))
        if len(chosen) >= max_num:
            break
    return chosen


def _ret(c: pd.Series, k: int) -> float | None:
    return float((c.iloc[-1] / c.iloc[-1 - k] - 1) * 100) if len(c) > k else None


def _last(s: pd.Series) -> float | None:
    v = s.iloc[-1]
    return None if pd.isna(v) else float(v)


def analyze(ticker: str, raw: pd.DataFrame, plan: dict | None = None, unit: str = "달러") -> Analysis:
    df = raw.dropna(subset=["Close"]).copy()
    c = df["Close"]
    df["MA20"], df["MA50"], df["MA200"] = (c.rolling(n).mean() for n in (20, 50, 200))
    sd = c.rolling(20).std()
    df["BBU"], df["BBL"] = df["MA20"] + 2 * sd, df["MA20"] - 2 * sd
    rsi = float(_rsi(c).iloc[-1])
    atr = float(_atr(df).iloc[-1])
    last, prev = float(c.iloc[-1]), float(c.iloc[-2])

    chans = sr_channels(df["High"].to_numpy(), df["Low"].to_numpy())
    sups = [x for x in chans if x[1] < last]
    ress = [x for x in chans if x[0] > last]
    sup = max(sups, key=lambda x: x[1]) if sups else None
    res = min(ress, key=lambda x: x[0]) if ress else None

    # 손절: 최소 ATR×2. 지지 구간 하단이 그보다 멀고 −12% 이내면 지지 하단 사용 (더 먼 쪽)
    stop = last - 2 * atr
    if sup and sup[0] < stop and sup[0] >= last * 0.88:
        stop = sup[0]

    ma20, ma50, ma200, bbu = _last(df["MA20"]), _last(df["MA50"]), _last(df["MA200"]), _last(df["BBU"])
    a = Analysis(
        ticker=ticker, df=df, last=last, prev=prev, asof=c.index[-1], rsi=rsi, atr=atr, stop=stop,
        sup=sup, res=res, ma20=ma20, ma50=ma50, ma200=ma200, bbu=bbu,
        atr_x=(last - ma50) / atr if ma50 else None,
        r5=_ret(c, 5), r63=_ret(c, 63), r126=_ret(c, 126), unit=unit,
    )
    a.signals = _signals(a, plan)
    a.easy, a.todo = _explain(a, plan)
    return a


def _hot(a: Analysis) -> bool:
    return a.rsi >= 70 or (a.bbu is not None and a.last > a.bbu) or (a.atr_x is not None and a.atr_x >= 5)


def _trigger_hit(a: Analysis, tr: dict) -> bool:
    return a.last > tr["price"] if tr["dir"] == "above" else a.last <= tr["price"]


def _signals(a: Analysis, plan: dict | None) -> list[tuple[str, str]]:
    s = []
    if a.last < a.stop:
        s.append(("bad", "손절가 아래"))
    elif (a.last - a.stop) / a.last < 0.03:
        s.append(("warn", "손절가 3% 이내 접근"))
    if a.ma50 is not None and a.last < a.ma50:
        s.append(("bad", "50일 평균 아래 (추세 약화)"))
    elif a.ma20 is not None and a.last < a.ma20:
        s.append(("warn", "20일 평균 아래"))
    elif a.ma20 and a.ma50 and a.ma20 > a.ma50:
        s.append(("good", "상승 추세 유지"))
    if a.ma200 is not None and a.last < a.ma200:
        s.append(("bad", "200일 평균 아래 (장기 약세)"))
    if a.r5 is not None and -5 <= a.r5 <= 0 and a.ma50 and a.last > a.ma50:
        s.append(("good", "눌림목 조건 충족 (5일 −5~0%)"))
    if a.rsi >= 70:
        s.append(("warn", f"RSI {a.rsi:.0f} 과열"))
    elif a.rsi <= 30:
        s.append(("info", f"RSI {a.rsi:.0f} 과매도"))
    if a.bbu is not None and a.last > a.bbu:
        s.append(("warn", "볼린저 상단 위 (단기 과열)"))
    if a.atr_x is not None and a.atr_x >= 5:
        s.append(("warn", f"50일선에서 ATR {a.atr_x:.1f}배 (과열)"))
    if a.res and a.last >= a.res[0] * 0.98:
        s.append(("info", f"천장 {a.res[0]:.1f} 바로 아래"))
    tr = (plan or {}).get("trigger")
    if tr:
        if _trigger_hit(a, tr):
            s.append(("good", f"{tr['label']} 도달"))
        else:
            s.append(("info", f"{tr['label']}까지 {(tr['price'] / a.last - 1) * 100:+.1f}%"))
    return s


def _f(v: float) -> str:
    return f"{v:,.0f}" if v >= 1000 else (f"{v:.1f}" if v >= 100 else f"{v:.2f}")


def _p(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"


def _rng(z: tuple[float, float], u: str) -> str:
    return f"{_f(z[0])}{u}" if abs(z[1] - z[0]) / z[0] < 0.002 else f"{_f(z[0])}~{_f(z[1])}{u}"


def _explain(a: Analysis, plan: dict | None) -> tuple[str, str]:
    easy = []
    hot = _hot(a)
    if a.ma50 is None:
        easy.append("데이터가 짧아 추세를 판단하기 어렵습니다.")
    elif a.last > a.ma50 and a.ma20 and a.ma20 > a.ma50:
        easy.append(f"평균선이 위로 정리된 상승 추세입니다. 주가가 50일 평균(약 {_f(a.ma50)}{a.unit})보다 {_p((a.last / a.ma50 - 1) * 100)} 위에 있습니다.")
    elif a.last > a.ma50:
        easy.append(f"50일 평균(약 {_f(a.ma50)}{a.unit}) 위에 있지만 20일 평균이 아직 그 아래라, 추세가 완전히 살아나진 않았습니다.")
    else:
        easy.append(f"50일 평균(약 {_f(a.ma50)}{a.unit}) 아래로 내려와 추세가 약해졌습니다.")
    if a.ma200 is not None and a.last < a.ma200:
        easy.append(f"1년 평균(200일, 약 {_f(a.ma200)}{a.unit})보다도 아래라 장기적으로 약한 종목입니다.")

    if a.r5 is not None:
        tail = ("최근 며칠 빠르게 올랐습니다." if a.r5 > 5 else "최근 며칠 올랐습니다." if a.r5 > 1.5
                else "최근 며칠은 보합입니다." if a.r5 >= -1.5 else "최근 며칠 쉬어 가는 중입니다." if a.r5 >= -5
                else "최근 조정이 큽니다.")
        lead = f"6개월 {_p(a.r126)}, " if a.r126 is not None else (f"3개월 {_p(a.r63)}, " if a.r63 is not None else "")
        easy.append(f"{lead}최근 5일 {_p(a.r5)}로 {tail}")

    if hot:
        why = ", ".join(x for x in [
            f"RSI {a.rsi:.0f}" if a.rsi >= 70 else None,
            "볼린저 상단 위" if a.bbu is not None and a.last > a.bbu else None,
            f"50일선에서 ATR {a.atr_x:.1f}배" if a.atr_x is not None and a.atr_x >= 5 else None,
        ] if x)
        easy.append(f"{why}로 과열이라, 지금 사면 비싸게 사는 타이밍입니다.")
    elif a.rsi <= 30:
        easy.append(f"RSI {a.rsi:.0f}로 많이 빠진 상태입니다. 반등할 수도 있지만 하락 추세 중이면 더 빠질 수 있습니다.")
    elif a.rsi >= 65:
        easy.append(f"RSI {a.rsi:.1f}로 과열(70)에 가깝습니다.")
    else:
        easy.append(f"과열은 아닙니다(RSI {a.rsi:.1f}).")

    easy.append(f"천장(예전에 막힌 가격대)은 {_rng(a.res, a.unit)}로 {_p((a.res[0] / a.last - 1) * 100)} 위에 있습니다." if a.res
                else "머리 위에 뚜렷한 천장이 없습니다.")
    if a.sup:
        easy.append(f"바닥(예전에 받친 가격대)은 {_rng(a.sup, a.unit)}로 {_p((a.sup[1] / a.last - 1) * 100)} 아래입니다.")
    easy.append(f"하루 평균 {a.atr / a.last * 100:.1f}% 움직이는 종목입니다.")

    todo = []
    plan = plan or {}
    tr = plan.get("trigger")
    if a.last < a.stop:
        todo.append("종가가 손절가 아래입니다. 보유 중이면 팀 규칙대로 정리를 검토합니다.")
    elif plan.get("now"):
        todo.append("팀 계획상 지금 진입하는 종목입니다.")
        if hot:
            todo.append(f"다만 과열이라 20일 평균(약 {_f(a.ma20)}{a.unit}) 근처까지 기다리는 것도 방법입니다.")
        elif a.ma50 is not None and a.last < a.ma50:
            todo.append("다만 50일 평균 아래로 내려와 추세가 약해졌으니 팀과 다시 확인합니다.")
        elif a.ma20 is not None and a.last < a.ma20:
            todo.append(f"20일 평균(약 {_f(a.ma20)}{a.unit}) 아래라, 걱정되면 절반만 먼저 사고 다음 종가를 봅니다.")
    elif tr:
        if _trigger_hit(a, tr):
            todo.append(f"계획한 진입 조건({tr['label']})에 도달했습니다. 진입을 검토합니다.")
        else:
            todo.append(f"계획한 진입 조건({tr['label']})까지 기다립니다. 지금 가격에서 {_p((tr['price'] / a.last - 1) * 100)} 거리입니다.")
    elif hot:
        todo.append(f"과열이 식을 때까지 기다립니다. 20일 평균(약 {_f(a.ma20)}{a.unit}) 쪽으로 내려오면 다시 봅니다.")
    elif a.ma50 is not None and a.last < a.ma50:
        todo.append(f"추세가 돌아설 때까지 지켜봅니다. 종가가 50일 평균(약 {_f(a.ma50)}{a.unit})을 다시 넘으면 검토합니다.")
    elif a.res and a.last >= a.res[0] * 0.97:
        todo.append(f"천장 {_f(a.res[0])}{a.unit}를 종가로 넘는지 확인한 뒤 들어갑니다.")
    elif a.r5 is not None and -5 <= a.r5 <= 0:
        todo.append("상승 추세 속 눌림목이라 진입 후보입니다.")
    else:
        todo.append("추세는 괜찮지만 지금 뚜렷한 진입 신호는 없습니다.")
    if a.last >= a.stop:
        todo.append(f"들어간다면 손절가는 종가 {_f(a.stop)}{a.unit}({_p((a.stop / a.last - 1) * 100)})입니다.")
    if not plan:
        todo.append("실적 발표일은 블룸버그 ERN <GO>로 확인하세요.")
    return " ".join(easy), " ".join(todo)
