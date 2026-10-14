"""Recent headlines (Yahoo Finance) summarized in Korean by Gemini."""
from __future__ import annotations

import datetime as dt

import yfinance as yf
from google import genai
from google.genai import errors, types

DEFAULT_MODEL = "gemini-flash-latest"  # 최신 Flash 모델을 가리키는 별칭
FALLBACK_MODELS = ["gemini-flash-lite-latest"]  # 기본 모델이 붐빌 때(503/429) 대신 쓸 모델

SYSTEM = (
    "You help a Korean university team in a stock-picking competition. "
    "Given recent headlines about one stock, explain in Korean, in at most 3 short bullet points, "
    "what is driving the stock right now and anything coming up (earnings, deals, guidance). "
    "Use only the headlines provided; if they don't explain the move, say so plainly. "
    "Write for a beginner, no jargon, no investment advice."
)


def headlines(ticker: str, n: int = 10) -> list[dict]:
    items = yf.Search(ticker, news_count=n).news or []
    out = []
    for it in items:
        ts = it.get("providerPublishTime")
        out.append({
            "title": it.get("title", ""),
            "publisher": it.get("publisher", ""),
            "link": it.get("link", ""),
            "time": dt.datetime.fromtimestamp(ts) if ts else None,
        })
    return out


def summarize(ticker: str, items: list[dict], api_key: str, model: str | None = None) -> str:
    # 일시적 과부하(429/5xx)는 SDK가 몇 번 다시 시도하고, 그래도 안 되면 예비 모델로 넘어간다
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=3, initial_delay=1.0, max_delay=8.0,
                                             http_status_codes=[429, 500, 502, 503, 504])))
    lines = "\n".join(
        f"- [{i['time']:%Y-%m-%d}] {i['title']} ({i['publisher']})" if i["time"] else f"- {i['title']} ({i['publisher']})"
        for i in items
    )
    models = [model or DEFAULT_MODEL] + [m for m in FALLBACK_MODELS if m != (model or DEFAULT_MODEL)]
    last_error: Exception | None = None
    for m in models:
        try:
            response = client.models.generate_content(
                model=m,
                contents=f"Stock: {ticker}\nHeadlines:\n{lines}",
                config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2),
            )
        except errors.APIError as e:
            if e.code in (429, 500, 502, 503, 504, 404):
                last_error = e
                continue
            raise
        text = (response.text or "").strip()
        if text:
            return text
    if last_error:
        raise last_error
    return "요약을 만들 수 없었습니다. 아래 헤드라인을 직접 확인하세요."
