# docs/adr — 아키텍처 결정 기록

설계가 바뀌는 결정은 코드보다 먼저 여기에 번호를 붙여 기록한다.

## 색인

| 번호 | 결정 | 상태 |
|---|---|---|
| 0001~0008 | v4 설계 확정 과정의 결정들 — **원문 미반입.** 결정 내용은 `02_상세설계_및_개발환경구축_v4.md`에 반영돼 있고 CLAUDE.md "v4에서 바뀐 결정"이 요약이다 | 원문 요청 중 |
| 0009 | 도구 `delegate_exploration` 폐기 → `query_code_graph` (사전 정의 쿼리만, 자유 질의 금지) | 원문 미반입, CLAUDE.md R4·contracts.md에 반영 |
| [0010](ADR-0010-llm-backend-switch.md) | LLM 백엔드 전환 | 승인 |
| [0011](ADR-0011-gateway-direct.md) | 사내 게이트웨이 직결(Azure OpenAI 호환), 시크릿은 환경변수·.env만 | 승인 |
| [0012](ADR-0012-langgraph-loop-record.md) | 테스트 작성 루프 LangGraph + 호출 기록·재생 | 승인 |
| [0013](ADR-0013-model-comparison-gpt.md) | 모델 비교(gpt 계열) | 승인 |
| [0014](ADR-0014-local-defect-benchmark.md) | Defects4J·EvoSuite 보류, 로컬 결함 세트로 대체 (v2: 12건 + 자기 검사) | 승인 |
| [0015](ADR-0015-scenario-alignment.md) | 시나리오 정합 — 명령 체계·건별 의도 출력·저장 후 재개 | 승인 |
| [0016](ADR-0016-no-conversation-compaction.md) | 대화 압축을 구현하지 않는다 — 단발 프롬프트 구조 | 승인 |
| [0017](ADR-0017-writer-skills.md) | 테스트 작성 워크플로우에 스킬 — 규칙 기반 선택, 도구 추가 없음 | 승인 |
| [0018](ADR-0018-mcp-server.md) | MCP 서버는 CLI 껍데기 — 도구 5개, 동기, 선택 의존성 | 승인 |

> ⚠️ 0001~0009 원문은 미반입 상태다. 기존 결정과 충돌이 의심되면 사용자에게 원문을 요청해 확인한다.
> 새 ADR은 0019부터.
