"""Bloomberg Trading Challenge — team chart tool.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from analysis import Analysis, analyze
from plan import PLAN

st.set_page_config(page_title="티커 차트 검색", page_icon="📈", layout="wide")

LEVEL_COLOR = {"good": "green", "warn": "orange", "bad": "red", "info": "violet"}
UNITS = {"USD": ("$", "달러"), "TWD": ("NT$", "대만달러"), "EUR": ("€", "유로"), "KRW": ("₩", "원"),
         "HKD": ("HK$", "홍콩달러"), "JPY": ("¥", "엔"), "GBP": ("£", "파운드"), "GBp": ("p", "펜스")}


@st.cache_data(ttl=86400, show_spinner=False)
def currency(ticker: str) -> str:
    try:
        return yf.Ticker(ticker).fast_info.currency or "USD"
    except Exception:
        return "USD"


@st.cache_data(ttl=300, show_spinner=False)
def load(ticker: str) -> pd.DataFrame | None:
    """1 year of daily bars; today's bar is intraday while the market is open (~15 min delay)."""
    df = yf.download(ticker, period="1y", interval="1d", auto_adjust=False, progress=False, multi_level_index=False)
    if df is None or df.empty or len(df.dropna(subset=["Close"])) < 30:
        return None
    return df


def chart(a: Analysis) -> go.Figure:
    df = a.df.iloc[-126:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["BBU"], line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=df.index, y=df["BBL"], line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(29,95,138,0.12)", name="볼린저밴드", hoverinfo="skip"))
    if a.sup:
        fig.add_hrect(y0=a.sup[0], y1=a.sup[1] if a.sup[1] > a.sup[0] else a.sup[0] * 1.003,
                      fillcolor="rgba(35,130,74,0.18)", line_width=0,
                      annotation_text=f"바닥 {a.sup[0]:.1f}", annotation_position="right")
    if a.res:
        fig.add_hrect(y0=a.res[0], y1=a.res[1] if a.res[1] > a.res[0] else a.res[0] * 1.003,
                      fillcolor="rgba(184,56,42,0.16)", line_width=0,
                      annotation_text=f"천장 {a.res[0]:.1f}", annotation_position="right")
    fig.add_hline(y=a.stop, line=dict(color="#b8382a", dash="dash", width=1.2),
                  annotation_text=f"손절 {a.stop:.1f}", annotation_position="bottom left")
    fig.add_trace(go.Scatter(x=df.index, y=df["MA200"], name="200일 평균", line=dict(color="#9a4fb0", width=1.2, dash="dot")))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA50"], name="50일 평균", line=dict(color="#1d5f8a", width=1.6)))
    fig.add_trace(go.Scatter(x=df.index, y=df["MA20"], name="20일 평균", line=dict(color="#d29a1d", width=1.2)))
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="종가", line=dict(color="#18212c", width=2)))
    fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.12, font=dict(size=11)), yaxis=dict(side="right"))
    return fig


def card(t: str, a: Analysis, plan: dict | None, sym: str) -> None:
    chg = (a.last / a.prev - 1) * 100
    head, btn = st.columns([5, 1])
    head.markdown(f"### {t} &nbsp; {sym}{a.last:,.2f} &nbsp; :{'green' if chg >= 0 else 'red'}[{chg:+.1f}%]")
    head.caption((plan or {}).get("note", "검색으로 추가한 종목") + f" · 데이터 {a.asof:%Y-%m-%d}")
    if btn.button("새로고침", key=f"r-{t}"):
        load.clear(t)
        st.rerun()
    st.plotly_chart(chart(a), width="stretch", key=f"c-{t}")
    st.markdown(" ".join(f":{LEVEL_COLOR[k]}-badge[{s}]" for k, s in a.signals))
    m = st.columns(6)
    m[0].metric("RSI", f"{a.rsi:.1f}")
    m[1].metric("5일", f"{a.r5:+.1f}%" if a.r5 is not None else "—")
    m[2].metric("6개월", f"{a.r126:+.1f}%" if a.r126 is not None else "—")
    m[3].metric("50일선 대비", f"{(a.last / a.ma50 - 1) * 100:+.1f}%" if a.ma50 else "—")
    m[4].metric("하루 변동폭", f"{a.atr / a.last * 100:.1f}%")
    m[5].metric("손절가", f"{sym}{a.stop:,.1f}", f"{(a.stop / a.last - 1) * 100:.1f}%", delta_color="off")
    st.markdown(f"**쉽게 말하면** {a.easy}")
    st.info(f"**할 일** {a.todo}")


def show(t: str) -> None:
    with st.container(border=True):
        try:
            df = load(t)
        except Exception as e:  # network / Yahoo hiccups
            st.error(f"{t}: 데이터를 받지 못했습니다. 잠시 뒤 새로고침하세요. ({type(e).__name__})")
            return
        if df is None:
            st.warning(f"{t}: 데이터를 찾지 못했습니다. 티커를 확인하세요. 미국 외 종목은 접미사가 필요합니다 (예: 대만 2330.TW, 독일 ADS.DE).")
            return
        cur = currency(t)
        sym, unit = UNITS.get(cur, (cur + " ", cur))
        card(t, analyze(t, df, PLAN.get(t), unit), PLAN.get(t), sym)


# ---------- page ----------
st.title("티커 차트 검색")
st.caption("Bloomberg Trading Challenge 팀 차트 도구 · Yahoo Finance 데이터 (장중 약 15분 지연, 5분마다 갱신) · 신호와 설명은 숫자에서 규칙으로 자동 작성되며 실적·뉴스는 반영하지 않습니다")

if "extra" not in st.session_state:
    qp = st.query_params.get("t", "")
    st.session_state.extra = [x for x in qp.split(",") if x]

with st.form("search", clear_on_submit=True):
    c1, c2 = st.columns([5, 1])
    q = c1.text_input("티커", placeholder="티커 입력 (예: NVDA, 2330.TW)", label_visibility="collapsed")
    if c2.form_submit_button("조회", width="stretch") and q.strip():
        t = re.sub(r"[^A-Z0-9.\-^=]", "", q.strip().upper())
        load.clear(t)  # 검색하면 항상 최신으로
        if t in st.session_state.extra:
            st.session_state.extra.remove(t)
        if t not in PLAN:
            st.session_state.extra.insert(0, t)
            st.query_params["t"] = ",".join(st.session_state.extra)
        st.session_state.focus = t

focus = st.session_state.get("focus")
if focus:
    st.subheader(f"검색 결과: {focus}")
    show(focus)

others = [x for x in st.session_state.extra if x != focus]
if others:
    st.subheader("검색한 종목")
    cols = st.columns(2)
    for i, t in enumerate(others):
        with cols[i % 2]:
            show(t)

for group, title in [("now", "오늘 진입"), ("wait", "대기 후 진입"), ("jack", "잭팟 후보")]:
    names = [t for t, p in PLAN.items() if p["group"] == group and t != focus]
    if not names:
        continue
    st.subheader(title)
    cols = st.columns(2)
    for i, t in enumerate(names):
        with cols[i % 2]:
            show(t)

st.divider()
st.caption("손절가: 최소 ATR×2, 지지 구간 하단이 더 멀고 −12% 이내면 그 값. 바닥·천장은 TradingView SR 채널 지표를 단순화한 계산입니다. 매매 결정은 팀 규칙을 따르세요.")
