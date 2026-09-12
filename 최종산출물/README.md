# 최종산출물

2026-09-13부터 새로 만드는 산출물은 전부 이 폴더에 둔다. `docs/` 아래 과거 문서는 더 이상 갱신하지 않는다
(참고용으로만 남긴다). 설계 결정의 원문은 `docs/adr/ADR-0026-impact-calls-and-embedding.md`.

| 파일 | 내용 | 재생성 |
|---|---|---|
| `architecture.drawio` | 상세 아키텍처 3페이지 — 1. 에이전트 구조 · 2. CLI 명령별 흐름 · 3. ADR-0026 변경분(영향 범위·임베딩 검색) | `python scripts/render_drawio.py 최종산출물/architecture.drawio` |
| `architecture-agent.png` · `architecture-cli.png` · `architecture-impact.png` | 위 3페이지 PNG | draw.io 데스크톱 `-x -f png --width 2400 -p <1\|2\|3>` |
| `architecture-infographic.drawio` | 인포그래픽 3페이지 — Agent Architecture · Agent Workflow · Impact & Memory | `python scripts/render_final_infographic.py 최종산출물/architecture-infographic.drawio` |
| `infographic-architecture.png` · `infographic-workflow.png` · `infographic-impact.png` | 위 3페이지 PNG | 위와 같음 |

편집은 draw.io(데스크톱 또는 diagrams.net)로 `.drawio`를 열어 하거나, 생성 스크립트를 고쳐 다시 만든다.
