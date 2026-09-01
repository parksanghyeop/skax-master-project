# contracts.md — 데이터 모델·도구 시그니처

모든 작업 전에 이 문서를 확인한다. 코드와 어긋나면 코드를 고치기 전에 사용자에게 알린다.

근거: `docs/02_상세설계_및_개발환경구축_v4.md` (이하 "v4"). v4는 개념 설계,
이 문서는 정확한 시그니처의 원천이다.

## 포트 (core/ports.py)

core가 바깥 세계와 만나는 인터페이스. 구현은 adapters/에만 둔다.

| 포트 | 시그니처 | 계약 |
|---|---|---|
| `SourceInspector` | `inspect(target: str) -> str` | 대상 소스 텍스트 반환. 없는 대상이면 예외 대신 안내 문자열(알려진 대상 목록 포함) |
| `TestRunner` | `run(selector: str) -> RunResult` | 선택한 테스트만 실행. 빈/공백 selector → `EmptySelectorError`(R5). 테스트 실패는 예외가 아니라 `passed=False` |
| `TestWriter` | `write(path: str, code: str) -> str` | 테스트 폴더 밖 경로는 쓰지 않고 거부 문자열(v4 제약 ④) |
| `SimilarTestFinder` | `find(target: str) -> str` | 모양이 닮은 기존 테스트 발췌. 없으면 안내 문자열 |
| `QualityChecker` | `check(path: str) -> str` | "통과"/"탈락" 선두의 결정적 검사 결과(R2) |
| `UserGate` | `ask(question: str) -> UserReply` | 반복 중단 지점. PoC는 자동 "계속" 스텁, 2단계에서 interrupt 실연결 |
| `CodeGraph` | `answer(query: str, target: str) -> str` | 그래프 질의(M4). 구현: GraphCodeGraph(그래프 실물)/ParsingCodeGraph(파싱 폴백). 답 상한 800토큰(도구 층 clip) |
| `TestCodeGenerator` | `generate(instruction, context, current_code, last_failure) -> str` | LLM은 이 포트 뒤(llm/generation.py)에만 있다 |

`target`·`selector` 문법은 어댑터가 해석한다 — core는 불투명 문자열로 취급.

## 데이터 모델

| 모델 | 필드 | 비고 |
|---|---|---|
| `RunResult` | `passed: bool`, `summary: str` | frozen dataclass. summary는 모델에게 그대로 보여줄 요약 |
| `EmptySelectorError` | (ValueError 하위) | 전체 테스트 실행 금지(R5)의 결정적 안전장치 |

## 샌드박스 (sandbox/docker_sandbox.py — adapters가 사용하는 내부 계약)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `DockerSandbox.run` | `run(image, command, mounts, workdir, network_enabled=False, timeout_seconds=600) -> SandboxResult` | 기본 네트워크 차단. 실패는 exit_code로 전달(예외 아님), 시간 초과는 exit_code=124 |
| `Mount` | `host_path, container_path, read_only=False` | read_only는 실행 단계의 의존성 캐시 보호용 |
| `SandboxResult` | `exit_code: int, output: str` | output은 stdout·stderr 합본 |

## Java 어댑터 (adapters/java)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `detect_maven_project` | `(path) -> MavenProject` | pom.xml 없으면 `NotAMavenProjectError` |
| `find_existing_test_class` | `(project) -> str \| None` | 예열용 기존 테스트 클래스 탐지 (없으면 None) |
| `read_package` (parsing) | `(source: str) -> str` | package 선언 읽기, 없으면 빈 문자열 — 테스트 저장 경로 계산용 |
| `JavaTestRunner.prepare` | `(warmup_selector: str) -> SandboxResult` | 네트워크 연결 상태에서 go-offline + 예열 1회. 빈 selector 거부(R5) |
| `JavaTestRunner.run` | `(selector: str) -> RunResult` | TestRunner 포트 구현. 네트워크 차단 + `-o` + 캐시 읽기 전용 |

## llm 계층 (R7 — 모든 LLM 호출의 유일한 통로)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `LlmClient` (포트) | `chat(messages: list[ChatMessage], model: str) -> ChatResponse` | 구현: GatewayClient(실호출) / RecordingClient(녹음) / ReplayClient(재생) |
| `ChatMessage` | `role: str, content: str` | role: system/user/assistant |
| `ChatResponse` | `content: str` | tool calling 확정(1주차 확인 3번) 시 필드 확장 |
| `RecordingClient` | `(inner, cassette_path)` | 호출마다 카세트(JSON) 갱신. 시크릿은 기록에 미포함 |
| `ReplayClient` | `(cassette_path)` | 순서대로 재생 + 요청 대조. 카세트 없음·소진·불일치 → `CassetteError`. **실호출 폴백 없음** |
| `GatewayClient` | 환경변수 `CTA_GATEWAY_URL`·`CTA_GATEWAY_API_KEY` 필수, `CTA_GATEWAY_API_VERSION` 선택 | Azure OpenAI 호환(ADR-0011): `/openai/deployments/{model}/chat/completions?api-version=...`, 인증 `api-key` 헤더. 없으면 `GatewayConfigError` |
| `make_llm_client` | `() -> (LlmClient, deployment 이름)` | 설정 `CTA_LLM_MODEL`(기본 gpt-4.1). 우선순위: 환경변수 > `.env` |

카세트 형식: `[{"request": {"model", "messages"}, "response": {"content"}}]` JSON 배열.

## 파이프라인 (core/pipeline — M5)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `ChangedSymbol` | `target, lines_added, lines_removed, signature_changed, diff_excerpt` | 변경 추출 출력. 구현: `GitChangeExtractor(project, base="HEAD")` — `--relative`로 하위 폴더 프로젝트 지원 |
| `Intent` | `category(bug_fix/refactor/new_feature/unclear), analysis` | 의도 분류 출력 — LLM 1회 호출(대분류+구체 분석). 파싱 실패·모르는 값 → unclear |
| `decide` | `(ChangedSymbol, Intent, tests_status) -> ActionDecision` | **규칙표 조회, LLM 금지(R2)**. tests_status: pass/fail/none |
| `ActionDecision` | `kind(create_test/no_action/escalate/ask), target, briefing, reason` | 기대값 자동 수정 행은 표에 없다(R3). refactor+fail→escalate, unclear→ask, refactor+none→ask |
| `IntentClassifier` (포트) | `classify(change_summary) -> Intent` | 구현: `llm/intent.PromptedIntentClassifier` (프롬프트 `classify_intent.md`) |
| `ChangeExtractor` (포트) | `extract() -> list[ChangedSymbol]` | 결정적 — 같은 diff면 같은 출력 |

## 코드 그래프 (graph/ — M4)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `GraphNode` | `kind("Class"/"Method"), key, props` | key: 클래스 `Calc`, 메서드 `Calc#add` (오버로드 미구분 — 알려진 한계) |
| `GraphEdge` | `kind, src, dst` | 확정 3종: DECLARES(클래스→메서드), CREATES(메서드→생성 클래스), COVERS(테스트 클래스→실측 실행 메서드) |
| `GraphStore` | `replace_project(project, nodes, edges)` / `neighbors(project, key, edge_kind, direction)` / `methods_by_kind(project, is_test)` | 구현: InMemoryGraphStore(테스트·폴백), Neo4jGraphStore(실물, 환경변수 `CTA_NEO4J_URI/USER/PASSWORD`) |
| `build_graph` (adapters/java) | `(MavenProject) -> (nodes, edges)` | 정적 파싱으로 DECLARES·CREATES. COVERS는 `JacocoCoverageCollector.collect_edges` |
| `parse_covered_methods` | `(jacoco_xml: str) -> set[str]` | 라인 커버>0 메서드 key. 생성자 제외. M6 커버리지 게이트가 재사용 |

쿼리 6종 중 M4 실응답: `verifying_tests`(COVERS 실측) · `how_to_create`(CREATES, 테스트 우선) ·
`similar_tests`(모양 거리). 후순위(안내 문장): `callers`(CALLS 추정 필요) · `implementations` · `touches_outside`.

## 도구 공통 규약

- 도구 반환은 예외가 아니라 **모델이 읽을 문자열**
- 길이 상한: `core.textlimit.clip(text)` 경유, `TOOL_OUTPUT_MAX_CHARS = 4000`
  (임시값 — v4 원문 확인 필요)

## 도구 6종 (R4 — core/tools/, 1도구 1파일)

v4 3절의 도구 표와 코드 식별자의 대응. 공통: 포트를 첫 인자로 받는 순수 함수,
반환은 clip을 거친 문장(예외 없음). `query_code_graph`의 쿼리 이름 6종은
`core/tools/query_code_graph.py`의 `KNOWN_QUERIES`가 원천이다.

| 코드 식별자 | v4 이름 | 입력 | 출력 |
|---|---|---|---|
| `inspect_target` | 대상 조사 | 대상 메서드 식별자 | 형태·의존·기존 테스트 요약문 |
| `query_code_graph` | 코드 그래프 조회 | 사전 정의 쿼리 종류 + 대상 (자유 쿼리 금지) | 짧은 답. PoC에서는 "비슷한 모양의 테스트는?"만 파싱 기반으로 실응답 |
| `write_test` | 테스트 쓰기 | 파일 위치 + 코드 | 컴파일·정적 분석 결과 |
| `run_tests` | 테스트 실행 | 실행할 테스트 목록 + 난수 시작값(seed) | 통과/실패 + 실패 내용 |
| `check_quality` | 품질 확인 | 확인할 범위 | 커버리지·뮤테이션 지표 요약 |
| `report_finding` | 한계 보고 | 발견한 문제 | 종료 |
