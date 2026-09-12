# 최종산출물

2026-09-13부터 새로 만드는 산출물은 전부 이 폴더에 둔다. `docs/` 아래 과거 문서는 더 이상 갱신하지 않는다
(참고용으로만 남긴다). 설계 결정의 원문은 `docs/adr/ADR-0026-impact-calls-and-embedding.md`.

| 파일 | 내용 |
|---|---|
| `최종보고.md` | 최종 보고서 — 한눈에 보기·목표·아키텍처·명령·이번 단계 작업(ADR-0026, 버그 7건)·검증 결과(테스트 314건, 평가 하네스)·운영/보안·한계와 다음 단계 |
| `cta-diagrams.drawio` | 그림 6장(6페이지). draw.io로 열어 편집 |
| `1-agent-architecture.png` | 인포그래픽 — Agent 구조 아키텍처(사용자 → CLI → 에이전트(메인+서브 3, 도구 6, 안전장치) ↔ LLM, 실행 장치·코드 그래프·판단 메모, 게이트 → 제안 → 반영) |
| `2-detailed-architecture.png` | 상세 아키텍처 — 층별 모듈(cli·core·adapters·graph·llm·sandbox), 작성 엔진 둘, 포트→어댑터, 안전장치, 상태 저장소 |
| `3-user-command-flows.png` | 사용자 관점 명령어별 흐름 — generate / maintain(--impact) / resolve / diff·apply·discard / graph·eval·demo 레인 |
| `4-graphdb-architecture.png` | 인포그래픽 — 코드 그래프(Neo4j) 구성: 채우기(정적 파싱·CALLS 추정·JaCoCo 실측) → 저장(GraphStore, 단일 라벨·관계) → 읽기(사전 정의 질의 4종, 도구·TestLocator·ImpactFinder), 폴백 |
| `5-cli-flows-infographic.png` | 인포그래픽 간소화 — 명령어별 흐름(명령 한 줄 = 카드 몇 장, LLM 호출 단계 표시, 종료 코드) — 3번의 발표용 축약판 |
| `6-project-structure.png` | 간소화 — 프로젝트 파일 구조 트리(파일 탐색기 모양): 루트 → 층 폴더 → 핵심 파일, 노드마다 한 줄 설명, 색 = 층 |

재생성: `python scripts/render_final_diagrams.py 최종산출물/cta-diagrams.drawio`
PNG: draw.io 데스크톱 `-x -f png --width 2400 -p <1|2|3|4|5|6>`
