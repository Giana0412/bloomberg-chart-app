"""Team chatbot: Gemini with the team's strategy log as context and the app's data as tools."""
from __future__ import annotations

import datetime as dt
import re
import urllib.request
from typing import Callable

from google import genai
from google.genai import errors, types

from news import DEFAULT_MODEL, FALLBACK_MODELS

SYSTEM_BASE = """너는 Bloomberg Global Trading Challenge에 나간 한국 대학생 팀의 투자 도우미야.
- 대회: 가상 $1M, 롱온리, 레버리지 없음, 단일 종목 20% 상한, WLS 지수 편입 종목만, 순위는 WLS 대비 상대 수익. 기간 2026-10-12 ~ 2026-11-13.
- 팀 목표: 10위권 공격형. 핵심 추세 종목 + 실적 이벤트 + 잭팟 후보, 나머지는 지수 바스켓에 보관.
- 팀 규칙: 실적 다음 날 시가가 전날 종가보다 +2% 이상이고 1시간 뒤에도 시가 위면 최대 5거래일 보유, 아니면 바로 매도.
  손절은 종가 기준, 최소 ATR×2 (지지 구간 하단이 더 멀고 −12% 이내면 그 값). 반도체 합계 30% 이내.
- 숫자(가격, 손절가, 실적일, 예상 변동폭, 포트폴리오)는 반드시 도구로 조회해서 답해. 기억이나 추측으로 숫자를 말하지 마.
- 초보자도 이해하게 쉬운 한국어로, 짧게. 결론을 먼저 말하고 근거는 2~4줄.
- 확실하지 않으면 그렇다고 말하고, 블룸버그 터미널에서 확인할 방법(예: ERN <GO>)을 알려 줘.
- 매수·매도는 팀이 결정한다. 너는 근거와 위험을 정리해 주는 역할이야."""


def fetch_doc_text(url_or_id: str) -> str:
    """Plain text of a Google Doc shared as 'anyone with the link can view'."""
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url_or_id)
    did = m.group(1) if m else url_or_id.strip()
    with urllib.request.urlopen(f"https://docs.google.com/document/d/{did}/export?format=txt", timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def make_tools(deps: dict[str, Callable]) -> list[Callable]:
    """deps: analyze(ticker)->Analysis|None, event(ticker)->dict, portfolio()->str,
    calendar(start, end, min_cap)->DataFrame, headlines(ticker)->list[dict]."""

    def chart_analysis(ticker: str) -> str:
        """현재 차트 상태: 가격, 추세, RSI, 손절가, 바닥·천장, 자동 신호, 쉬운 설명.

        Args:
            ticker: Yahoo 티커 (예: TWLO, 2330.TW).
        """
        a = deps["analyze"](ticker.upper())
        if a is None:
            return f"{ticker}: 데이터를 찾지 못함"
        sig = ", ".join(s for _, s in a.signals) or "없음"
        return (f"{a.ticker} {a.asof:%Y-%m-%d} 가격 {a.last:.2f} (전일 대비 {(a.last / a.prev - 1) * 100:+.1f}%), "
                f"RSI {a.rsi:.1f}, 5일 {a.r5:+.1f}%, 6개월 {a.r126 if a.r126 is None else round(a.r126, 1)}%, "
                f"50일선 {a.ma50 and round(a.ma50, 2)}, 200일선 {a.ma200 and round(a.ma200, 2)}, "
                f"손절가 {a.stop:.2f} ({(a.stop / a.last - 1) * 100:+.1f}%), 바닥 {a.sup}, 천장 {a.res}. "
                f"신호: {sig}. 설명: {a.easy} 할 일: {a.todo}")

    def earnings_event(ticker: str) -> str:
        """다음 실적 발표일과 옵션 시장이 예상하는 변동폭(ATM 스트래들, 첫 만기까지).

        Args:
            ticker: Yahoo 티커.
        """
        e = deps["event"](ticker.upper())
        mv = e.get("implied_move")
        return (f"{ticker.upper()}: 실적일 {e.get('earnings')}, 옵션 만기 {e.get('expiry')}, "
                f"예상 변동폭 {'없음' if mv is None else f'±{mv:.1f}%'}, 현재가 {e.get('price')}")

    def team_portfolio() -> str:
        """팀 포트폴리오 현황: 총 평가액, 지수 대비 수익, 종목별 비중·수익률·손절가."""
        return deps["portfolio"]()

    def earnings_calendar(start: str, end: str, min_cap_billion: float = 2.0) -> str:
        """기간 내 미국 실적 발표 종목 (시가총액 큰 순, 날짜별 최대 25개).

        Args:
            start: 시작일 YYYY-MM-DD.
            end: 종료일 YYYY-MM-DD.
            min_cap_billion: 시가총액 하한 (십억 달러).
        """
        df = deps["calendar"](dt.date.fromisoformat(start), dt.date.fromisoformat(end), min_cap_billion * 1e9)
        df = df[~df["symbol"].str.fullmatch(r"[A-Z]{4}[FY]")]  # 해외 장외(OTC) 티커 제외
        if df.empty:
            return "해당 기간 실적 종목 없음"
        out = []
        for d, g in df.groupby("date"):
            out.append(f"{d}: " + ", ".join(f"{r.symbol}({r.timing}, ${r.cap / 1e9:.0f}B)" for r in g.head(25).itertuples()))
        return "\n".join(out)

    def news_headlines(ticker: str) -> str:
        """종목의 최근 뉴스 헤드라인 (Yahoo).

        Args:
            ticker: Yahoo 티커.
        """
        items = deps["headlines"](ticker.upper())
        if not items:
            return "최근 뉴스 없음"
        return "\n".join(f"- {i['time']:%m/%d} {i['title']} ({i['publisher']})" if i["time"] else f"- {i['title']}"
                         for i in items)

    return [chart_analysis, earnings_event, team_portfolio, earnings_calendar, news_headlines]


def system_prompt(plan: dict, context_text: str | None) -> str:
    plan_lines = "\n".join(f"- {t}: {p.get('note', '')}" for t, p in plan.items())
    parts = [SYSTEM_BASE, f"오늘 날짜: {dt.date.today():%Y-%m-%d}", f"팀 계획 종목:\n{plan_lines}"]
    if context_text:
        parts.append("아래는 팀이 지금까지 전략을 논의한 대화 기록이야. 결정된 규칙과 판단의 근거로 참고해. "
                     "다만 그 안의 숫자는 당시 기준이니 지금 숫자는 도구로 다시 확인해.\n<team_log>\n"
                     + context_text + "\n</team_log>")
    return "\n\n".join(parts)


def ask(api_key: str, history: list[dict], question: str, tools: list[Callable], system: str,
        model: str | None = None) -> tuple[str, list[str]]:
    """One user turn. `history` holds {"role": "user"|"model", "text": ...}; returns (answer, tools called).

    The SDK runs the tool calls itself (automatic function calling); overload errors are retried,
    then the lighter model is tried, same as the news summary.
    """
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=3, initial_delay=1.0, max_delay=8.0,
                                             http_status_codes=[429, 500, 502, 503, 504])))
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8),
        temperature=0.3,
    )
    models = [model or DEFAULT_MODEL] + [m for m in FALLBACK_MODELS if m != (model or DEFAULT_MODEL)]
    last_error: Exception | None = None
    for m in models:
        try:
            response = client.models.generate_content(model=m, contents=contents, config=config)
        except errors.APIError as e:
            if e.code in (429, 500, 502, 503, 504, 404):
                last_error = e
                continue
            raise
        called = [f"{p.function_call.name}({', '.join(str(v) for v in (p.function_call.args or {}).values())})"
                  for c in (response.automatic_function_calling_history or [])
                  for p in (c.parts or []) if p.function_call]
        answer = (response.text or "").strip() or "(빈 응답)"
        history.append({"role": "user", "text": question})
        history.append({"role": "model", "text": answer})
        return answer, called
    raise last_error  # type: ignore[misc]
