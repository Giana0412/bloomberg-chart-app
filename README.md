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
