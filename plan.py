"""Team plan: which tickers show by default, and their entry conditions.

Edit this file to change the watchlist. `trigger` turns an entry condition into a signal.
"""

PLAN = {
    "TWLO": dict(group="now", now=True, note="오늘 진입 15% · 실적 10/29~30"),
    "TSM": dict(group="now", now=True, note="오늘 진입 12% · ADR 허용 확인 · 실적 10/15"),
    "ASML": dict(group="now", now=True, note="오늘 진입 13% · 실적 10/14"),
    "MEDP": dict(group="wait", note="대기 10% · 10/19~20 진입 · 실적 10/21~22"),
    "HNGE": dict(group="wait", note="대기 10% · 92~95달러로 식으면 진입 · 실적 11/2~3",
                 trigger=dict(dir="below", price=95, label="진입 구간 95달러 이하")),
    "SN": dict(group="wait", note="대기 10% · 종가 194.5 돌파 시 진입 · 실적 11/5",
               trigger=dict(dir="above", price=194.5, label="돌파 기준 194.5달러")),
    "FRO": dict(group="wait", note="대기 10% · 20일 평균(약 51달러) 알림",
                trigger=dict(dir="below", price=51, label="알림가 51달러")),
    "DINO": dict(group="wait", note="대기 0~10% · 10/22 발레로 실적 후 결정 · 실적 10/28"),
    "SMCI": dict(group="jack", note="잭팟 후보 최대 10% · 실적 11/3~4 · 39.6 바닥 깨지면 제외"),
}
