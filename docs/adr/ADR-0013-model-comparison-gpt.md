# ADR-0013: 모델 비교 실험은 게이트웨이 GPT 계열 deployment 기준

- 상태: 승인 (2026-09-01, ADR-0011의 귀결)
- 관련: v4 5절(모델 여러 종 비교), phase2 스킬 "모델 3종(Kimi/Qwen/GLM) 비교"

## 배경

v4와 phase2 스킬은 사내 게이트웨이가 Kimi/Qwen/GLM을 제공한다고 전제했다.
실제 게이트웨이(ADR-0011)는 GPT 계열 deployment를 제공한다:
chat용 gpt-4.1(-mini), gpt-4o(-mini), gpt-5(-mini), gpt-5.4, gpt-5.6-luna,
임베딩용 text-embedding-3-large/small, ada-002.

## 결정

1. 평가 하네스(M7)의 모델 비교는 **같은 문제 세트에서 GPT 계열 deployment 간
   비교**로 진행한다. 1차 비교군: gpt-4.1(기본값) vs gpt-5(현재 사용) vs
   gpt-4.1-mini(비용 하한 탐색).
2. "모델 이름은 설정(CTA_LLM_MODEL)·실험 기록에 항상 명시"는 유지 — 수치는
   프롬프트·모델·데이터셋 버전에 묶어 기록한다(고도화 규칙).
3. 임베딩 보조 검색(v4 4.1 ④)은 text-embedding-3-small을 1차 후보로 한다
   (대용량 아님 + 비용 우선. large와의 품질 비교는 필요 시 하네스로).
