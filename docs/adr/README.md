# docs/adr — 아키텍처 결정 기록

설계가 바뀌는 결정은 코드보다 먼저 여기에 번호를 붙여 기록한다.

## 색인

| 번호 | 결정 | 상태 |
|---|---|---|
| 0001~0008 | v4 설계 확정 과정의 결정들 — **원문 미반입.** 결정 내용은 `02_상세설계_및_개발환경구축_v4.md`에 반영돼 있고 CLAUDE.md "v4에서 바뀐 결정"이 요약이다 | 원문 요청 중 |
| 0009 | 도구 `delegate_exploration` 폐기 → `query_code_graph` (사전 정의 쿼리만, 자유 질의 금지) | 원문 미반입, CLAUDE.md R4·contracts.md에 반영 |
| [0010](ADR-0010-llm-backend-switch.md) | LLM 백엔드 전환 | 폐기 — 0011로 대체 |
| [0011](ADR-0011-gateway-direct.md) | 사내 게이트웨이 직결(Azure OpenAI 호환), 시크릿은 환경변수·.env만 | 승인 |
| [0012](ADR-0012-langgraph-loop-record.md) | 테스트 작성 루프 LangGraph + 호출 기록·재생 | 일부 대체 — 루프 구조는 0024, 기록·재생 원칙은 유지 |
| [0013](ADR-0013-model-comparison-gpt.md) | 모델 비교(gpt 계열) | 승인 |
| [0014](ADR-0014-local-defect-benchmark.md) | Defects4J·EvoSuite 보류, 로컬 결함 세트로 대체 (v2: 12건 + 자기 검사) | 승인 |
| [0015](ADR-0015-scenario-alignment.md) | 시나리오 정합 — 명령 체계·건별 의도 출력·저장 후 재개 | 승인 |
| [0016](ADR-0016-no-conversation-compaction.md) | 대화 압축을 구현하지 않는다 — 단발 프롬프트 구조 | 폐기 — 0024로 대체 |
| [0017](ADR-0017-writer-skills.md) | 테스트 작성 워크플로우에 스킬 — 규칙 기반 선택, 도구 추가 없음 | 승인 |
| [0018](ADR-0018-mcp-server.md) | MCP 서버는 CLI 껍데기 — 도구 5개, 동기, 선택 의존성 | 폐기 — 0021로 대체 |
| [0019](ADR-0019-local-runner.md) | 로컬 실행 모드 — `LocalSandbox`, 같은 `Sandbox` 프로토콜 | 일부 대체 — 기본값·`--fast` 의미는 0022 |
| [0020](ADR-0020-intent-unclear-reduction.md) | 의도 모름(unclear) 축소 — 작성자 지정 의도(`--intent`/`--message`/`resolve --as`), 의도 세트 측정. 단서 확대·기준치는 보류 | 승인 |
| [0021](ADR-0021-remove-mcp-server.md) | MCP 서버 제거 — 진입점은 CLI 하나(발표·시연 볼륨 축소) | 승인 |
| [0022](ADR-0022-local-runner-default.md) | 실행 장치 기본값은 로컬 — Docker 샌드박스는 `--runner docker`, `--fast`는 게이트 생략만 (R6 재정의) | 승인 |
| [0023](ADR-0023-llm-cost.md) | LLM 비용 — 기존 테스트 파일에는 새 멤버만 출력(합치기는 어댑터), 추론 강도 기본 low, 토큰 내역 기록 | 승인 |
| [0024](ADR-0024-deep-agents.md) | 테스트 작성 루프를 Deep Agents(메인 1 + 서브 3)로 — 규칙표·게이트는 하네스에, LLM 경로는 LangChain 모델 + 카세트 v2, `--engine deep` 단계 도입 | 승인 |
| [0025](ADR-0025-tools-redefinition.md) | R4 재정의 — 고유 도구 6개 + 하네스 내장 도구, 내장 쓰기 도구 deny, 사람 개입 도구 `ask_user`(메인만) | 승인 |
| [0026](ADR-0026-impact-calls-and-embedding.md) | 영향 범위 분석 — CALLS 엣지(확신도) 도입·`callers` 실응답·`--impact` 파생 건, 임베딩 검색은 판단 메모(자연어)에만 | 승인 — 구현 완료(임베딩 실호출은 키 있는 환경에서 확인) |

> ⚠️ 0001~0009 원문은 미반입 상태다. 기존 결정과 충돌이 의심되면 사용자에게 원문을 요청해 확인한다.
> 새 ADR은 0027부터.
