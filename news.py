"""Recent headlines (Yahoo Finance) summarized in Korean by Claude."""
from __future__ import annotations

import datetime as dt

import anthropic
import yfinance as yf

MODEL = "claude-opus-5-5"

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


def summarize(ticker: str, items: list[dict], api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    lines = "\n".join(
        f"- [{i['time']:%Y-%m-%d}] {i['title']} ({i['publisher']})" if i["time"] else f"- {i['title']} ({i['publisher']})"
        for i in items
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Stock: {ticker}\nHeadlines:\n{lines}"}],
    )
    if response.stop_reason == "refusal":
        return "요약을 만들 수 없었습니다. 아래 헤드라인을 직접 확인하세요."
    return "".join(b.text for b in response.content if b.type == "text").strip()
