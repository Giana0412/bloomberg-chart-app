# 티커 차트 검색

Bloomberg Trading Challenge 팀용 차트 도구. 티커를 검색하면 Yahoo Finance 일봉(장중 약 15분 지연)으로 차트, 손절가, 자동 신호, 쉬운 설명을 보여 줍니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 팀 공유 (Streamlit Community Cloud, 무료)

1. 이 폴더를 GitHub 저장소로 올립니다.
2. https://share.streamlit.io 에 GitHub 계정으로 로그인 → **Create app** → 저장소와 `app.py`를 선택 → Deploy.
3. 나온 `https://….streamlit.app` 링크를 팀에 공유합니다.
4. 팀 밖에 안 보이게 하려면 앱 설정 → Sharing에서 팀원 이메일만 허용합니다.

## 관심 종목 바꾸기

`plan.py`의 `PLAN`을 고치면 기본으로 보이는 종목과 진입 조건(`trigger`)이 바뀝니다. 고친 뒤 GitHub에 올리면 배포된 앱도 자동으로 갱신됩니다.

## 계산 규칙

- 손절가: 최소 ATR×2 아래. 지지 구간 하단이 그보다 멀고 −12% 이내면 그 값.
- 바닥·천장: TradingView "Support Resistance Channels" 지표를 단순화한 계산.
- 신호와 설명은 숫자에서 규칙으로 자동 작성되며 실적·뉴스는 반영하지 않습니다.

## 추가 기능 설정 (Streamlit Cloud → 앱 Settings → Secrets)

```toml
PORTFOLIO_SHEET = "https://docs.google.com/spreadsheets/d/…"   # 포트폴리오 탭 (시트는 '링크가 있는 모든 사용자: 뷰어')
GEMINI_API_KEY = "…"                                            # 뉴스 AI 요약 + 팀 챗봇 (Google AI Studio 키)
GEMINI_MODEL = "gemini-flash-latest"                            # 선택
CHAT_CONTEXT_DOC = "https://docs.google.com/document/d/…"       # 챗봇 배경 지식 (여러 개면 쉼표로 구분, 링크 뷰어 공유)
```

포트폴리오 시트 첫 줄: `ticker, amount_usd, entry_price, entry_date, note`. `entry_price`가 비면 `entry_date` 종가를 씁니다.

## 챗봇으로 거래 기록하기 (시트 쓰기)

1. 포트폴리오 시트 → 확장 프로그램 → Apps Script → `apps_script/Code.gs` 내용을 붙여넣고 저장
2. 프로젝트 설정(톱니바퀴) → 스크립트 속성 → `TOKEN` 추가 (긴 비밀 문자열)
3. 배포 → 새 배포 → 유형 "웹 앱", 실행 "나", 액세스 "모든 사용자" → 배포 → 권한 허용
4. Streamlit Secrets에 추가:

```toml
SHEET_WRITE_URL = "https://script.google.com/macros/s/…/exec"
SHEET_WRITE_TOKEN = "2번의 TOKEN"
```

챗봇에 "ASML 전량 1690에 팔았어", "DDOG 10만 달러 샀어", "NVAX 레이더에 넣어줘"라고 말하면 제안이 뜨고, [확인]을 눌러야 시트(보유 종목·trades·watch 탭)에 반영됩니다.

블룸버그 포트 현황(`[보유 중] …`)을 붙여넣으면 보유 종목을 맞추고, 헤더의 P&L·Rel P&L을 `snapshots` 탭에 남겨 포트폴리오 탭 맨 위에 "블룸버그 공식" 숫자로 보여 줍니다.

`Code.gs`를 고친 뒤에는 Apps Script에 다시 붙여넣고 **배포 → 배포 관리 → ✏️ → 버전: 새 버전 → 배포**를 해야 반영됩니다 (URL은 그대로).

## 포트폴리오 탭 경고

- 손절가: 해외 종목도 달러로 바꿔 표시 (현지 가격은 따로)
- 실적 반응 규칙: 발표 뒤 첫 장 시가 ≥ 전날 종가 +2%이고 1시간 뒤에도 시가 위면 "보유"(최대 5거래일), 아니면 "매도". 실적 전부터 들고 있던 종목만 경고
- 반도체 합계 30% 초과, 현금 15% 초과
