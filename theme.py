"""Bloomberg-terminal-style dark look: palette, page CSS, header bar, Plotly template.

Widget/table/alert colours come from .streamlit/config.toml; keep the hex values there in sync with these.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG = "#050505"
PANEL = "#0E0E0E"
BORDER = "#262626"
TEXT = "#E6E6E6"
MUTED = "#8C8C8C"
AMBER = "#FF9F1C"
BLUE = "#4FA3FF"
GREEN = "#2FD47A"
RED = "#FF4D4D"
VIOLET = "#B48CFF"
MONO = "'IBM Plex Mono', ui-monospace, Menlo, monospace"


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


pio.templates["terminal"] = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0A0A0A",
    font=dict(family=MONO, color="#BDBDBD", size=11),
    colorway=[AMBER, BLUE, GREEN, VIOLET, "#F5C451", RED, MUTED],
    xaxis=dict(gridcolor="#1A1A1A", zerolinecolor=BORDER, linecolor="#333333"),
    yaxis=dict(gridcolor="#1A1A1A", zerolinecolor=BORDER, linecolor="#333333"),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="#161616", bordercolor=AMBER, font=dict(family=MONO, color=TEXT)),
))
pio.templates.default = "plotly_dark+terminal"

CSS = f"""
<style>
[data-testid="stDecoration"] {{ display: none; }}
.block-container {{ padding-top: 2.2rem; max-width: 1500px; }}

/* header bar */
.term-head {{ display: flex; align-items: center; gap: .9rem; flex-wrap: wrap;
  background: {AMBER}; color: #000; padding: .35rem .8rem; font-family: {MONO}; }}
.term-head .logo {{ background: #000; color: {AMBER}; font-weight: 600; padding: .05rem .45rem; letter-spacing: .08em; }}
.term-head .title {{ font-weight: 600; letter-spacing: .12em; }}
.term-head .sub {{ opacity: .75; font-size: .82rem; }}
.term-head .clock {{ margin-left: auto; font-size: .82rem; font-weight: 500; }}
.term-strip {{ font-family: {MONO}; font-size: .74rem; color: {MUTED}; border-bottom: 1px solid {BORDER};
  padding: .3rem .1rem .45rem; margin-bottom: .6rem; }}
.term-strip b {{ color: {AMBER}; font-weight: 500; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 0; background: #0B0B0B; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{ padding: .5rem 1.1rem; font-family: {MONO}; letter-spacing: .03em; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: {AMBER} !important; background: #151515; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {AMBER}; }}

/* section headings */
h3 {{ color: {AMBER} !important; font-size: 1rem !important; font-weight: 600 !important; letter-spacing: .04em;
  border-bottom: 1px solid {BORDER}; padding-bottom: .3rem !important; margin-top: .6rem; }}

/* metric panels */
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {BORDER}; border-left: 3px solid {AMBER};
  padding: .55rem .8rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .78rem; letter-spacing: .03em; }}
[data-testid="stMetricValue"] {{ font-family: {MONO}; font-variant-numeric: tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-family: {MONO}; }}
/* 차트 카드 안의 지표 줄(한 행에 6칸 이상)은 칸이 좁아 숫자가 잘린다 — 그 행만 작게 */
[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) [data-testid="stMetric"] {{ padding: .35rem .45rem; border-left-width: 2px; }}
[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) [data-testid="stMetricValue"],
[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) [data-testid="stMetricValue"] * {{ font-size: .95rem !important; }}
[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) [data-testid="stMetricLabel"] p {{ font-size: .68rem; }}
[data-testid="stHorizontalBlock"]:has(> div:nth-child(6)) [data-testid="stMetricDelta"] {{ font-size: .66rem; padding: 0 .25rem; }}

/* expanders, bordered containers, alerts */
[data-testid="stExpander"] details {{ border-color: {BORDER}; background: {PANEL}; }}
[data-testid="stExpander"] summary {{ font-family: {MONO}; }}
[data-testid="stAlert"] {{ border-left: 3px solid currentColor; }}

/* briefing cards */
[class*="st-key-brief-"] {{ background: {PANEL}; border-top: 2px solid {AMBER} !important; }}
.brief-h {{ font-family: {MONO}; color: {AMBER}; font-size: .78rem; letter-spacing: .1em; margin: 0 0 .25rem; }}
.brief-h span {{ color: {MUTED}; letter-spacing: 0; }}
.brief-top {{ display: flex; gap: .6rem; align-items: baseline; flex-wrap: wrap; font-family: {MONO};
  border: 1px solid {BORDER}; background: {PANEL}; padding: .55rem .8rem; margin: .3rem 0 .8rem; }}
.brief-top .big {{ color: {TEXT}; font-size: 1.05rem; font-weight: 600; }}
.brief-top .tag {{ color: #000; background: {AMBER}; font-size: .7rem; padding: .05rem .4rem; }}
.brief-top .muted {{ color: {MUTED}; font-size: .78rem; margin-left: auto; }}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header() -> None:
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    ny = now.astimezone(ZoneInfo("America/New_York"))
    st.markdown(
        f"""<div class="term-head"><span class="logo">BTC</span><span class="title">TEAM TERMINAL</span>
<span class="sub">Bloomberg Trading Challenge</span>
<span class="clock">SEOUL {now:%m/%d %H:%M} · NY {ny:%m/%d %H:%M}</span></div>
<div class="term-strip"><b>DATA</b> Yahoo Finance · 장중 약 15분 지연 · 5분마다 갱신 &nbsp; <b>SIGNAL</b> 숫자에서 규칙으로 자동 작성</div>""",
        unsafe_allow_html=True)
