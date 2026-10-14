"""Bloomberg Trading Challenge — team chart tool.

Run locally:  streamlit run app.py
Secrets (Streamlit Cloud → App settings → Secrets, or .streamlit/secrets.toml):
  PORTFOLIO_SHEET = "<Google Sheet URL>"   # 포트폴리오 탭
  GEMINI_API_KEY = "..."                  # AI 뉴스 요약 (Google AI Studio)
  GEMINI_MODEL = "gemini-flash-latest"     # 선택
  CHAT_CONTEXT_DOC = "<Google Doc URL>"    # 챗봇 배경 지식 (팀 전략 대화 기록)
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

import chatbot
import events
import news
import portfolio as pf
import screen_import
from analysis import Analysis, analyze
from plan import PLAN

st.set_page_config(page_title="티커 차트 검색", page_icon="📈", layout="wide")

CHALLENGE_START = pd.Timestamp("2026-10-12")
LEVEL_COLOR = {"good": "green", "warn": "orange", "bad": "red", "info": "violet"}
UNITS = {"USD": ("$", "달러"), "TWD": ("NT$", "대만달러"), "EUR": ("€", "유로"), "KRW": ("₩", "원"),
         "HKD": ("HK$", "홍콩달러"), "JPY": ("¥", "엔"), "GBP": ("£", "파운드"), "GBp": ("p", "펜스")}


def secret(name: str) -> str | None:
    try:
        return st.secrets.get(name) or None
    except Exception:  # no secrets file locally
        return None


# ---------- data ----------
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


@st.cache_data(ttl=300, show_spinner=False)
def close_usd(ticker: str) -> pd.Series | None:
    df = load(ticker)
    if df is None:
        return None
    s = df["Close"].dropna()
    cur = currency(ticker)
    if cur == "USD":
        return s
    pence = cur == "GBp"
    fx = load(f"{'GBP' if pence else cur}USD=X")
    if fx is None:
        return None
    rate = fx["Close"].reindex(s.index, method="ffill")
    return s * rate / (100 if pence else 1)


@st.cache_data(ttl=3600, show_spinner=False)
def event(ticker: str) -> dict:
    return events.earnings_event(ticker)


@st.cache_data(ttl=900, show_spinner=False)
def heads(ticker: str) -> list[dict]:
    return news.headlines(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def ai_summary(ticker: str, titles: tuple[str, ...], _items: list[dict]) -> str:
    return news.summarize(ticker, _items, secret("GEMINI_API_KEY"), secret("GEMINI_MODEL"))


def analysis_for(t: str) -> tuple[Analysis | None, str]:
    df = load(t)
    if df is None:
        return None, "$"
    sym, unit = UNITS.get(currency(t), (currency(t) + " ", currency(t)))
    return analyze(t, df, PLAN.get(t), unit), sym


# ---------- chart tab ----------
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


def news_box(t: str) -> None:
    with st.expander("최근 뉴스 · AI 요약"):
        key = f"news-{t}"
        if not st.session_state.get(key):
            if st.button("뉴스 불러오기", key=f"nb-{t}"):
                st.session_state[key] = True
                st.rerun()
            return
        try:
            items = heads(t)
        except Exception as e:
            st.error(f"뉴스를 받지 못했습니다 ({type(e).__name__}).")
            return
        if not items:
            st.write("최근 뉴스가 없습니다.")
            return
        if secret("GEMINI_API_KEY"):
            try:
                with st.spinner("Gemini가 요약하는 중"):
                    st.markdown(ai_summary(t, tuple(i["title"] for i in items), items))
            except Exception as e:
                code = getattr(e, "code", None)
                if code in (429, 503):
                    st.warning("Gemini 서버가 지금 붐벼서 요약하지 못했습니다(예비 모델까지 시도함). 잠시 뒤 '다시 요약'을 눌러 주세요.")
                elif code in (400, 401, 403):
                    st.warning("Gemini API 키가 맞지 않거나 권한이 없습니다. 앱 Secrets의 GEMINI_API_KEY를 확인하세요.")
                else:
                    st.warning(f"AI 요약 실패: {type(e).__name__}: {str(e)[:200]}. 헤드라인을 직접 확인하세요.")
                if st.button("다시 요약", key=f"rs-{t}"):
                    st.rerun()
        else:
            st.caption("AI 요약을 쓰려면 앱 Secrets에 GEMINI_API_KEY를 넣으세요.")
        for i in items:
            when = f"{i['time']:%m/%d %H:%M} · " if i["time"] else ""
            st.markdown(f"- [{i['title']}]({i['link']}) <span style='color:gray;font-size:0.85em'>{when}{i['publisher']}</span>",
                        unsafe_allow_html=True)


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
    news_box(t)


def show(t: str) -> None:
    with st.container(border=True):
        try:
            a, sym = analysis_for(t)
        except Exception as e:  # network / Yahoo hiccups
            st.error(f"{t}: 데이터를 받지 못했습니다. 잠시 뒤 새로고침하세요. ({type(e).__name__})")
            return
        if a is None:
            st.warning(f"{t}: 데이터를 찾지 못했습니다. 티커를 확인하세요. 미국 외 종목은 접미사가 필요합니다 (예: 대만 2330.TW, 독일 ADS.DE).")
            return
        card(t, a, PLAN.get(t), sym)


def tab_charts() -> None:
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


# ---------- portfolio tab ----------
def tab_portfolio() -> None:
    sheet = secret("PORTFOLIO_SHEET") or st.session_state.get("sheet")
    if not sheet:
        st.info("팀 보유 종목을 적은 구글 시트 링크가 필요합니다. 시트는 '링크가 있는 모든 사용자: 뷰어'로 공유해야 읽을 수 있습니다.")
        url = st.text_input("구글 시트 링크", placeholder="https://docs.google.com/spreadsheets/d/…")
        if url:
            st.session_state.sheet = url
            st.rerun()
        return
    try:
        pos = pf.read_positions(sheet)
    except Exception as e:
        st.error(f"시트를 읽지 못했습니다. 공유 설정이 '링크가 있는 모든 사용자: 뷰어'인지, 첫 줄 열 이름이 맞는지 확인하세요. ({e})")
        return
    if pos.empty:
        st.warning("시트에 보유 종목이 없습니다.")
        return

    closes = {t: close_usd(t) for t in pos["ticker"].unique()}
    closes[pf.BENCH] = close_usd(pf.BENCH)
    table, s = pf.value(pos, closes, CHALLENGE_START)

    c = st.columns(5)
    c[0].metric("총 평가액", f"${s['total']:,.0f}", f"{s['port_ret']:+.2f}%")
    c[1].metric(f"지수({pf.BENCH}) 수익률", f"{s['bench_ret']:+.2f}%" if s["bench_ret"] is not None else "—")
    c[2].metric("지수 대비 (순위 기준)", f"{s['rel']:+.2f}%p" if s["rel"] is not None else "—",
                f"${s['rel_usd']:+,.0f}" if s["rel_usd"] is not None else None)
    c[3].metric("투자금", f"${s['invested']:,.0f}")
    c[4].metric("현금", f"${s['cash']:,.0f}", f"{s['cash'] / pf.NOTIONAL * 100:.1f}%", delta_color="off")
    st.caption(f"지수 수익률은 대회 시작일({CHALLENGE_START:%m/%d}) 기준. 대회 벤치마크 WLS는 Yahoo에 없어 비슷한 전 세계 지수 ETF {pf.BENCH}로 대신 계산합니다. 매수가 칸이 비어 있으면 매수일 종가를 씁니다.")

    alerts, rows = [], []
    for _, r in table.iterrows():
        t = r["ticker"]
        a, _sym = (None, "$")
        try:
            a, _sym = analysis_for(t)
        except Exception:
            pass
        ev = event(t)
        ed = ev.get("earnings")
        dday = (ed - dt.date.today()).days if ed else None
        if a is not None:
            if a.last < a.stop:
                alerts.append(("bad", f"{t}: 종가가 손절가({a.stop:,.1f}) 아래입니다. 정리를 검토하세요."))
            elif (a.last - a.stop) / a.last < 0.03:
                alerts.append(("warn", f"{t}: 손절가({a.stop:,.1f})까지 3% 이내입니다."))
        if "value" in r and pd.notna(r.get("value")) and r["value"] / pf.NOTIONAL * 100 >= 18:
            alerts.append(("warn", f"{t}: 1M 대비 {r['value'] / pf.NOTIONAL * 100:.1f}%로 20% 상한에 가깝습니다."))
        if dday is not None and 0 <= dday <= 3:
            alerts.append(("info", f"{t}: 실적 발표 D-{dday} ({ed:%m/%d}). 실적 반응 규칙을 미리 정해 두세요."))
        rows.append({
            "종목": t, "투자금($)": r["amount_usd"], "매수가": r.get("entry_used"), "현재가": r.get("last"),
            "수익률(%)": r.get("ret"), "손익($)": r.get("pnl"), "현재 비중(%)": r.get("weight_now"),
            "20% 상한 여유(%p)": r.get("cap_room"),
            "손절가": a.stop if a else None, "신호": " · ".join(s_ for _, s_ in (a.signals if a else [])[:3]),
            "실적": f"{ed:%m/%d} (D-{dday})" if ed and dday is not None and dday >= 0 else (f"{ed:%m/%d}" if ed else "—"),
            "메모": r.get("note", ""),
        })

    if alerts:
        st.subheader("확인할 것")
        for k, msg in alerts:
            {"bad": st.error, "warn": st.warning, "info": st.info}[k](msg)
    st.subheader("보유 종목")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "투자금($)": st.column_config.NumberColumn(format="%,.0f"),
        "매수가": st.column_config.NumberColumn(format="%.2f"),
        "현재가": st.column_config.NumberColumn(format="%.2f"),
        "수익률(%)": st.column_config.NumberColumn(format="%+.2f"),
        "손익($)": st.column_config.NumberColumn(format="%+,.0f"),
        "현재 비중(%)": st.column_config.NumberColumn(format="%.1f"),
        "20% 상한 여유(%p)": st.column_config.NumberColumn(format="%.1f"),
        "손절가": st.column_config.NumberColumn(format="%.1f"),
    })

    # 포트폴리오 vs 지수 추이
    idx = closes[pf.BENCH].index if closes[pf.BENCH] is not None else None
    if idx is not None:
        idx = idx[idx >= CHALLENGE_START]
        if len(idx) >= 1:
            total = pd.Series(pf.NOTIONAL - table["amount_usd"].sum(), index=idx)
            for _, r in table.iterrows():
                cs = closes.get(r["ticker"])
                if cs is None or pd.isna(r.get("entry_used")):
                    continue
                px = cs.reindex(idx, method="ffill")
                held = (r["amount_usd"] / r["entry_used"]) * px
                start = r["entry_date"] if pd.notna(r["entry_date"]) else CHALLENGE_START
                total += held.where(idx >= start, r["amount_usd"])
            b = closes[pf.BENCH].reindex(idx)
            bench = pf.NOTIONAL * b / b.iloc[0]
            fig = go.Figure([go.Scatter(x=idx, y=total, name="우리 팀", line=dict(color="#1d5f8a", width=2.2)),
                             go.Scatter(x=idx, y=bench, name=f"지수({pf.BENCH})", line=dict(color="#9aa8b8", width=1.6, dash="dot"))])
            fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), hovermode="x unified",
                              legend=dict(orientation="h", y=-0.15), yaxis=dict(tickformat="$,.0f"))
            st.subheader("팀 vs 지수")
            st.plotly_chart(fig, width="stretch")
    st.caption("보유 종목을 바꾸려면 구글 시트를 고치면 됩니다. 앱은 5분마다 새로 읽습니다.")


# ---------- earnings radar tab ----------
@st.cache_data(ttl=21600, show_spinner=False)
def calendar(start: dt.date, end: dt.date, min_cap: float) -> pd.DataFrame:
    return events.earnings_calendar(start, end, min_cap)


@st.cache_data(ttl=3600, show_spinner=False)
def import_screen(source: str | bytes, filename: str = "") -> pd.DataFrame:
    rows = screen_import.read_export(source, filename)
    mapping = screen_import.map_tickers(rows["Ticker"].tolist())
    rows.insert(1, "Yahoo", rows["Ticker"].map(mapping))
    return rows


def team_tickers() -> set[str]:
    out = set(PLAN)
    sheet = secret("PORTFOLIO_SHEET") or st.session_state.get("sheet")
    if sheet:
        try:
            out |= set(pf.read_positions(sheet)["ticker"])
        except Exception:
            pass
    return out


def add_to_radar(tickers: list[str]) -> None:
    cur = st.session_state.setdefault("radar_extra", [])
    cur += [t for t in tickers if t and t not in cur]


def section_calendar() -> None:
    st.subheader("실적 캘린더")
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    weeks = []
    w = monday
    while w <= events.CHALLENGE_END:
        weeks.append(w)
        w += dt.timedelta(days=7)
    c1, c2, c3 = st.columns([2, 2, 2])
    week = c1.selectbox("주", weeks, format_func=lambda d: f"{d:%m/%d} ~ {d + dt.timedelta(days=4):%m/%d} 주")
    min_cap = c2.select_slider("시가총액 하한", options=[1e9, 2e9, 5e9, 1e10, 5e10],
                               value=2e9, format_func=lambda v: f"${v / 1e9:,.0f}B")
    us_only = c3.toggle("해외 OTC 제외", value=True, help="BWAGF처럼 F/Y로 끝나는 5글자 해외 장외 티커를 숨깁니다.")
    try:
        cal = calendar(week, week + dt.timedelta(days=4), min_cap)
    except Exception as e:
        st.error(f"캘린더를 받지 못했습니다 ({type(e).__name__}). 잠시 뒤 다시 시도하세요.")
        return
    if us_only:
        cal = cal[~cal["symbol"].str.fullmatch(r"[A-Z]{4}[FY]")]
    team = team_tickers()
    cols = st.columns(5)
    for i in range(5):
        d = week + dt.timedelta(days=i)
        day = cal[cal["date"] == d]
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"**{'월화수목금'[i]} {d:%m/%d}** · {len(day)}개")
                show_n = 15
                for _, r in day.head(show_n).iterrows():
                    tag = {"BMO": "장전", "AMC": "장후"}.get(r["timing"], "")
                    name = f":blue-badge[{r['symbol']}]" if r["symbol"] in team else f"`{r['symbol']}`"
                    st.markdown(f"{name} <span style='color:gray;font-size:0.8em'>{tag} ${r['cap'] / 1e9:,.0f}B</span>",
                                unsafe_allow_html=True)
                if len(day) > show_n:
                    with st.expander(f"+{len(day) - show_n}개 더"):
                        st.markdown(" ".join(f"`{x}`" for x in day["symbol"].iloc[show_n:]))
    st.caption("파란 배지는 팀 계획·보유 종목. 장전(BMO)은 개장 전, 장후(AMC)는 마감 후 발표. Yahoo 기준이며 날짜가 바뀔 수 있으니 ERN <GO>로 확인하세요.")
    pick = st.multiselect("레이더에 추가할 종목", cal["symbol"].tolist(), placeholder="이 주 실적 종목 중 골라서 아래 레이더로 보내기")
    if pick and st.button("선택 종목 레이더에 추가"):
        add_to_radar(pick)
        st.success(f"{len(pick)}종목을 레이더에 추가했습니다.")


def section_import() -> None:
    st.subheader("스크린 가져오기")
    st.caption("블룸버그 EQS 결과를 엑셀로 내보낸 파일이나 그 구글 시트 링크를 넣으면 티커를 Yahoo 형식으로 바꿔 줍니다. 시트는 '링크가 있는 모든 사용자: 뷰어'여야 합니다.")
    c1, c2 = st.columns(2)
    url = c1.text_input("구글 시트 링크", key="screen_url", placeholder="https://docs.google.com/spreadsheets/d/…")
    up = c2.file_uploader("또는 파일 (xlsx/csv)", type=["xlsx", "xls", "csv"], key="screen_file")
    if not url and not up:
        return
    try:
        with st.spinner("티커 확인 중 (20초 정도)"):
            rows = import_screen(up.getvalue(), up.name) if up else import_screen(url)
    except Exception as e:
        st.error(f"스크린을 읽지 못했습니다. 첫 열이 'XXXX US Equity' 형식인지, 공유 설정이 맞는지 확인하세요. ({e})")
        return
    us_only = st.toggle("미국 종목만", value=True, help="옵션 데이터(예상 변동폭)는 미국 종목만 나옵니다.")
    view = rows[rows["Ticker"].str.contains(r" (?:US|UN|UW|UQ) Equity$")] if us_only else rows
    missing = rows[rows["Yahoo"].isna()]["Ticker"].tolist()
    st.write(f"{len(rows)}종목 중 {rows['Yahoo'].notna().sum()}개 변환 · 지금 표시 {len(view)}개")
    st.dataframe(view, hide_index=True, width="stretch")
    if missing:
        st.caption("Yahoo에서 찾지 못한 종목: " + ", ".join(missing) + " (말레이시아·인도 종목은 기호 체계가 달라 수동 확인 필요)")
    ok = view["Yahoo"].dropna().tolist()
    b1, b2 = st.columns(2)
    if b1.button(f"레이더에 추가 ({len(ok)}종목)", disabled=not ok):
        add_to_radar(ok)
        st.success("아래 레이더 표에 추가했습니다. '레이더 실행'을 누르세요.")
    if b2.button("차트 검색 탭에 추가", disabled=not ok):
        extra = st.session_state.setdefault("extra", [])
        extra[:0] = [t for t in ok if t not in extra and t not in PLAN]
        st.query_params["t"] = ",".join(extra)
        st.success("차트 검색 탭의 '검색한 종목'에 추가했습니다.")


def section_radar() -> None:
    st.subheader("실적 레이더")
    st.markdown("실적 발표일과 **옵션 시장이 예상하는 변동폭**(만기까지의 ATM 스트래들 가격 ÷ 주가)을 보여 줍니다. "
                "잭팟 기준은 ±15% 이상, 대회 종료(11/13) 전 발표, 상승 추세입니다.")
    base = list(PLAN) + [t for t in sorted(team_tickers()) if t not in PLAN]
    base += [t for t in st.session_state.get("radar_extra", []) if t not in base]
    extra = st.text_input("추가로 볼 후보 티커 (쉼표로 구분)", placeholder="예: ALAB, CRDO, RBRK")
    tickers = base + [t for t in re.split(r"[,\s]+", extra.upper()) if t and t not in base]
    c1, c2 = st.columns([3, 1])
    run = c1.button(f"레이더 실행 ({len(tickers)}종목)", type="primary")
    if c2.button("추가한 종목 비우기"):
        st.session_state.radar_extra = []
        st.rerun()
    if not run and not st.session_state.get("radar"):
        st.caption("옵션 데이터를 종목마다 받아서 종목 수에 따라 1~3분 걸립니다. 결과는 1시간 저장됩니다.")
        return
    st.session_state.radar = True
    rows = []
    bar = st.progress(0.0, text="옵션 데이터 받는 중")
    for i, t in enumerate(tickers):
        bar.progress((i + 1) / len(tickers), text=f"{t} 확인 중")
        try:
            ev = event(t)
            a, _ = analysis_for(t)
        except Exception:
            continue
        ed, mv = ev.get("earnings"), ev.get("implied_move")
        if ed and ed < dt.date.today():  # Yahoo가 지난 실적일만 줄 때
            ed = None
        dday = (ed - dt.date.today()).days if ed else None
        in_window = ed is not None and dt.date.today() <= ed <= events.CHALLENGE_END
        trend = None if a is None or a.ma50 is None else ("상승" if a.last > a.ma50 else "약세")
        jackpot = in_window and mv is not None and mv >= 15 and trend == "상승" and (a.r126 or 0) > 0
        rows.append({"종목": t, "실적일": ed, "D-day": dday, "대회 기간 안": in_window,
                     "예상 변동폭(±%)": mv, "옵션 만기": ev.get("expiry"),
                     "6개월(%)": a.r126 if a else None, "RSI": a.rsi if a else None, "추세(50일선)": trend,
                     "잭팟 기준 충족": jackpot})
    bar.empty()
    if not rows:
        st.warning("결과가 없습니다.")
        return
    df = pd.DataFrame(rows).sort_values(["잭팟 기준 충족", "대회 기간 안", "실적일"], ascending=[False, False, True], na_position="last")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "실적일": st.column_config.DateColumn(format="MM/DD"),
        "예상 변동폭(±%)": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=30),
        "6개월(%)": st.column_config.NumberColumn(format="%+.1f"),
        "RSI": st.column_config.NumberColumn(format="%.0f"),
    })
    st.caption("예상 변동폭은 실적일 이후 첫 만기까지의 전체 기간을 포함해 실적 하루 움직임보다 조금 큽니다. "
               "예상 변동폭이 아주 작은데 최근 급등했다면 인수합병 등으로 가격이 묶였을 수 있으니 뉴스를 확인하세요. "
               "미국 외 종목은 옵션 데이터가 없을 수 있습니다.")
    if st.button("다시 계산"):
        event.clear()
        st.rerun()


def tab_radar() -> None:
    section_calendar()
    st.divider()
    section_import()
    st.divider()
    section_radar()


# ---------- chatbot tab ----------
@st.cache_data(ttl=600, show_spinner=False)
def chat_context() -> str | None:
    doc = secret("CHAT_CONTEXT_DOC")
    if not doc:
        return None
    try:
        return chatbot.fetch_doc_text(doc)
    except Exception:
        return None


def portfolio_text() -> str:
    sheet = secret("PORTFOLIO_SHEET") or st.session_state.get("sheet")
    if not sheet:
        return "포트폴리오 시트가 설정되지 않음"
    pos = pf.read_positions(sheet)
    closes = {t: close_usd(t) for t in pos["ticker"].unique()}
    closes[pf.BENCH] = close_usd(pf.BENCH)
    table, s = pf.value(pos, closes, CHALLENGE_START)
    lines = [f"총 평가액 ${s['total']:,.0f} ({s['port_ret']:+.2f}%), 지수({pf.BENCH}) {s['bench_ret']:+.2f}%, "
             f"지수 대비 {s['rel']:+.2f}%p, 현금 ${s['cash']:,.0f}"]
    for _, r in table.iterrows():
        a, _ = analysis_for(r["ticker"])
        lines.append(f"- {r['ticker']}: 투자 ${r['amount_usd']:,.0f}, 매수가 {r.get('entry_used', float('nan')):.2f}, "
                     f"현재 {r.get('last', float('nan')):.2f}, 수익률 {r.get('ret', float('nan')):+.2f}%, "
                     f"비중 {r.get('weight_now', float('nan')):.1f}%"
                     + (f", 손절가 {a.stop:.2f}" if a else ""))
    return "\n".join(lines)


def tab_chat() -> None:
    key = secret("GEMINI_API_KEY")
    if not key:
        st.info("팀 챗봇을 쓰려면 앱 Secrets에 GEMINI_API_KEY를 넣으세요.")
        return
    ctx = chat_context()
    st.caption(("팀 전략 대화 기록을 참고해서 답합니다. " if ctx else "팀 전략 대화 기록이 아직 연결되지 않았습니다(CHAT_CONTEXT_DOC). ")
               + "가격·손절가·실적일·포트폴리오는 질문할 때마다 앱 데이터를 새로 조회합니다. (Gemini)")
    hist = st.session_state.setdefault("chat_history", [])
    for m in hist:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            if m.get("tools"):
                st.caption("조회: " + " · ".join(m["tools"]))
            st.markdown(m["text"])
    c1, c2 = st.columns([5, 1])
    if c2.button("대화 지우기") and hist:
        st.session_state.chat_history = []
        st.rerun()
    q = st.chat_input("예: TWLO 지금 손절가 어디야? / 다음 주 실적 중 잭팟 후보 있어?")
    if not q:
        return
    st.chat_message("user").markdown(q)
    deps = {
        "analyze": lambda t: analysis_for(t)[0],
        "event": event,
        "portfolio": portfolio_text,
        "calendar": calendar,
        "headlines": heads,
    }
    with st.chat_message("assistant"):
        try:
            with st.spinner("데이터 조회하고 생각하는 중"):
                answer, called = chatbot.ask(key, hist, q, chatbot.make_tools(deps),
                                             chatbot.system_prompt(PLAN, ctx), secret("GEMINI_MODEL"))
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (429, 503):
                st.error("Gemini 서버가 지금 붐벼서 답하지 못했습니다(예비 모델까지 시도함). 잠시 뒤 다시 물어봐 주세요.")
            elif code in (400, 401, 403):
                st.error("Gemini API 키가 맞지 않거나 권한이 없습니다. 앱 Secrets의 GEMINI_API_KEY를 확인하세요.")
            else:
                st.error(f"답변을 만들지 못했습니다: {type(e).__name__}: {str(e)[:200]}")
            return
        hist[-1]["tools"] = called
        if called:
            st.caption("조회: " + " · ".join(called))
        st.markdown(answer)


# ---------- page ----------
st.title("티커 차트 검색")
st.caption("Bloomberg Trading Challenge 팀 도구 · Yahoo Finance 데이터 (장중 약 15분 지연, 5분마다 갱신) · 신호와 설명은 숫자에서 규칙으로 자동 작성됩니다")
t1, t2, t3, t4 = st.tabs(["차트 검색", "포트폴리오", "실적 레이더", "팀 챗봇"])
with t1:
    tab_charts()
with t2:
    tab_portfolio()
with t3:
    tab_radar()
with t4:
    tab_chat()
st.divider()
st.caption("손절가: 최소 ATR×2, 지지 구간 하단이 더 멀고 −12% 이내면 그 값. 바닥·천장은 TradingView SR 채널 지표를 단순화한 계산입니다. 매매 결정은 팀 규칙을 따르세요.")
