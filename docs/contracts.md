# contracts.md — 데이터 모델·도구 시그니처

모든 작업 전에 이 문서를 확인한다. 코드와 어긋나면 코드를 고치기 전에 사용자에게 알린다.

근거: `docs/02_상세설계_및_개발환경구축_v4.md` (이하 "v4"). v4는 개념 설계,
이 문서는 정확한 시그니처의 원천이다. 시나리오 정합 결정은 ADR-0015.

## 포트 (core/ports.py)

core가 바깥 세계와 만나는 인터페이스. 구현은 adapters/에만 둔다.

| 포트 | 시그니처 | 계약 |
|---|---|---|
| `SourceInspector` | `inspect(target: str) -> str` | 대상 소스 텍스트 반환. 없는 대상이면 예외 대신 안내 문자열(알려진 대상 목록 포함). target은 `Class`, `Class#m`, `Class#m1,m2` |
| `TestRunner` | `run(selector: str) -> RunResult` | 선택한 테스트만 실행. 빈/공백 selector → `EmptySelectorError`(R5). 테스트 실패는 예외가 아니라 `passed=False` |
| `TestWriter` | `write(path: str, code: str) -> str` | 테스트 폴더 밖 경로는 쓰지 않고 거부 문자열(v4 제약 ④) |
| `SimilarTestFinder` | `find(target: str) -> str` | 모양이 닮은 기존 테스트 발췌. 없으면 안내 문자열 |
| `QualityChecker` | `check(path: str) -> str` | "통과"/"탈락" 선두의 결정적 검사 결과(R2) |
| `UserGate` | `ask(question: str) -> UserReply` | 반복 중단 지점. interrupt 실연결(InterruptUserGate) |
| `CodeGraph` | `answer(query: str, target: str) -> str` | 그래프 질의(M4). 구현: GraphCodeGraph(그래프 실물)/ParsingCodeGraph(파싱 폴백). 답 상한 800토큰(도구 층 clip) |
| `TestCodeGenerator` | `generate(instruction, context, current_code, last_failure) -> str` | LLM은 이 포트 뒤(llm/generation.py)에만 있다 |
| `ChangeExtractor` | `extract() -> ChangeSet` | 결정적 — 같은 diff면 같은 출력. 구현 `GitChangeExtractor` |
| `IntentClassifier` | `classify(change: ChangedSymbol, change_set: ChangeSet, memos: str = "") -> Intent` | 변경 **한 건당** LLM 1회. 구현 `llm/intent.PromptedIntentClassifier`. memos는 참고 자료일 뿐 규칙표를 우회 못 함 |
| `TestLocator` | `find(target: str) -> list[str]` | 대상을 검증하는 기존 테스트 selector. 구현: `GraphTestLocator(store, project_key)`(COVERS 실측, cli) / `ReferencingTestLocator`(소스 참조 파싱 폴백, adapters). 선택은 `cli/graph_access.try_open_store`(접속 확인 질의 후 결정) |

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
| `parse_target` / `parse_methods` (parsing) | `(target) -> (class, method_field)` / `(field) -> list[str]` | 클래스 자리는 FQN 허용(마지막 마디만 사용), 메서드 자리는 쉼표 목록 |
| `strip_methods` (parsing) | `(source, names: set[str]) -> str` | 지정 메서드 본문 제거 — 사람 허용 테스트를 assert 비교에서 제외할 때 |
| `JavaTestRunner.prepare` | `(warmup_selector: str) -> SandboxResult` | 네트워크 연결 상태에서 go-offline + 예열 1회. 빈 selector 거부(R5) |
| `JavaTestRunner.run` | `(selector: str) -> RunResult` | TestRunner 포트 구현. 네트워크 차단 + `-o` + 캐시 읽기 전용 |
| `select_methods` (materials) | `(project, class_file, max_methods, only=None, include_all=False) -> (list[MethodPlan], skipped)` | 공개·미참조 메서드를 확인 항목 많은 순으로 N개. only는 지정 실행 |
| `enumerate_check_items` (materials) | `(method_text, start_line) -> tuple[CheckItem]` | 분기·경계값·예외·null 항목을 정규식으로 열거(결정적) |
| `describe_construction` (materials) | `(project, type_name) -> ConstructionHint` | 직접 생성(표준/builder/값 객체/record/enum) 또는 mock(인터페이스·저장소) |
| `collect_materials` / `render_materials` | `-> Materials` / `-> str` | 재료 묶음 = 메서드·확인 항목·생성법·기존 테스트 파일·대상 라인. render는 writer의 `extra_context` |
| `check_item_satisfaction` (materials) | `(items, line_coverage) -> int` | 항목 줄 실행(분기는 전부 실행) 기준의 충족 수 — 근사 |
| `parse_failed_tests` / `count_tests_run` / `describe_attempt` (failures) | 실행 출력 → `FailedTest(name, test_class, expected, actual, message)` / 합계 / 회차 한 줄 요약 | 화면 문구의 원천 — LLM 없음 |
| `compare_test_asserts` / `render_changes` (assert_report) | `(before_src, after_src) -> list[AssertChange]` / `-> str` | 테스트 메서드 단위 전/후 + 엄격함 점수(같음 4 > 참/거짓 3 > null 2 > null 아님 1) |
| `GitChangeExtractor.old_source` / `old_main_sources` | `(file_rel) -> str \| None` / `(change_set) -> dict` | base 시점 소스(git show). 재발 방지 게이트 입력 |

## llm 계층 (R7 — 모든 LLM 호출의 유일한 통로)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `LlmClient` (포트) | `chat(messages: list[ChatMessage], model: str) -> ChatResponse` | 구현: GatewayClient(실호출) / RecordingClient(녹음) / ReplayClient(재생) / MeteredClient(합산 래퍼) |
| `ChatMessage` | `role: str, content: str` | role: system/user/assistant |
| `ChatResponse` | `content: str, usage_tokens: int = 0` | usage_tokens는 게이트웨이 `usage.total_tokens`. 모르면 0 |
| `MeteredClient` | `(inner)`; `.calls`, `.total_tokens` | 호출 수·토큰 합산 — "소요 … 토큰" 출력용 |
| `RecordingClient` | `(inner, cassette_path)` | 호출마다 기록(JSON) 갱신. 시크릿은 기록에 미포함. 응답에 usage_tokens 포함 |
| `ReplayClient` | `(cassette_path)` | 순서대로 재생 + 요청 대조. 기록 없음·소진·불일치 → `CassetteError`. **실호출 폴백 없음** |
| `GatewayClient` | 환경변수 `CTA_GATEWAY_URL`·`CTA_GATEWAY_API_KEY` 필수, `CTA_GATEWAY_API_VERSION` 선택 | Azure OpenAI 호환(ADR-0011): `/openai/deployments/{model}/chat/completions?api-version=...`, 인증 `api-key` 헤더. 없으면 `GatewayConfigError` |
| `make_llm_client` | `() -> (LlmClient, deployment 이름)` | 설정 `CTA_LLM_MODEL`(기본 gpt-4.1). 우선순위: 환경변수 > `.env` |

기록 형식: `[{"request": {"model", "messages"}, "response": {"content", "usage_tokens"}}]` JSON 배열.

## 파이프라인 (core/pipeline)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `ChangedSymbol` | `target, lines_added, lines_removed, signature_changed, diff_excerpt, access_changed=False, comment_only=False, file_rel="", change_line=0` | 변경 추출 출력 + 단서. comment_only면 LLM 없이 trivial |
| `ChangeSet` | `symbols: list[ChangedSymbol], commit_message="", issue_refs=()` | 변경 단위 공통 단서. 미커밋 변경이면 commit_message 빈 값 |
| `Intent` | `category(bug_fix/refactor/new_feature/trivial/unclear), analysis, confidence(0~1), evidence: tuple[str]` | 파싱 실패·모르는 값 → unclear(confidence 0). **화면에 전부 출력된다** |
| `decide` | `(ChangedSymbol, Intent, tests_status) -> ActionDecision` | **규칙표 조회, LLM 금지(R2)**. tests_status: pass/fail/none |
| `ActionDecision` | `kind(create_test/no_action/escalate/ask), target, briefing, reason` | 기대값 자동 수정 행은 표에 없다(R3). refactor+fail→escalate, unclear→ask, refactor+none→ask, trivial→no_action |
| `analyze_changes` (maintain) | `(change_set, classifier, locator, runner, memo_lookup=None, progress=None) -> list[ChangeAnalysis]` | 건별 분류 → 검증 테스트 실행(같은 묶음 1회) → 규칙표. comment_only는 분류기 호출 없이 `TRIVIAL_INTENT` |
| `ChangeAnalysis` | `change, intent, tests, tests_status, run_summary, decision, memos` | 화면 블록(①②…)과 후속 처리의 단위 |

## 테스트 작성 서브그래프 (core/writer_graph)

| 항목 | 계약 |
|---|---|
| `WriterState` | 기존 키 + `extra_context: str`(호출부 재료, 수집 결과 뒤에 붙음) + `history: list[{"attempt","write_result","run_result"}]`(회차 기록). 둘 다 선택 — 없으면 빈 값 |
| 상한 | `MAX_TOTAL_ATTEMPTS = 8`, `ASK_EVERY_ATTEMPTS = 4` (SC-001 5단계) |
| `classify_failure` | `(last_run, prev_run) -> auto/ask/impossible` | 환경 표식→impossible, 동일 실패 반복→ask |
| `InterruptUserGate` / `invoke_with_interrupts` | LangGraph interrupt 실연결 | 정지→질문→답(계속/중지/힌트)→같은 지점 재개. checkpointer 필수 |

## 품질 게이트 (결정적, LLM 금지 R2)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `GateConfig` / `load_gate_config` | `(project_root) -> GateConfig` | `cta.toml` [gates]로 조정: line_min(0.80), branch_min(0.70), max_retries(3), mutation_min(0.5) |
| `Gate` (포트) | `name; check() -> GateResult(name, passed, reason)` | 예외 없이 판정. 측정 불가 = 탈락(보수적) |
| `run_gates` | `(list[Gate]) -> GateReport` | 단락 없이 전부 실행 — 탈락 사유를 한 번에 모은다 |
| `snapshot_baseline` | `(project) -> SourceBaseline(asserts, skip_counts, file_hashes, test_sources)` | 에이전트 실행 **전** 기준선 |
| `AssertIntegrityGate` | ① `(project, baseline, authorized_tests=None)` | 테스트 메서드 단위 전/후 비교 — 삭제·완화 탈락(사유에 점수). authorized_tests(사람이 지정한 실패 테스트)만 제외 |
| `SkipAnnotationGate` | ② | @Disabled/@Ignore 신규 부착 탈락 (FQN 우회 포함) |
| `FileScopeGate` | ③ | 소스 전체(main 포함) 해시 대조 — 허용 목록 밖 변경 탈락 |
| `CoverageGate` | ④ `.last_lines` | JaCoCo 실측: 대상 라인·분기 기준 미달 탈락. last_lines는 확인 항목 충족 계산에 재사용 |
| `MutationGate` | ⑤ `(…, target_methods: set[str] \| None)`, `.last_score` | PIT(overlay pom): 대상 메서드들의 변형 검출률 < 기준 탈락. `measure_mutation`이 전후 비교와 공유 |
| `BugReproductionGate` | ⑥ `regression` `(project, runner, old_sources, selector)` | 수정 전 소스로 바꿔 끼우고 실행 → **통과하면 탈락**. 파일은 finally로 복구. bug_fix create_test에만 부착 |
| `generate_with_gates` (core/submit) | `-> SubmitResult(status, ...)` | 생성→게이트, 탈락 사유를 지침서에 붙여 재시도(max_retries), 소진 시 human_review |

## CLI 보관소 (cli/)

| 항목 | 계약 |
|---|---|
| 제안 `proposals.py` | `<프로젝트>/.cta/proposals/<이름>.java + .json`. status accepted/needs_review. apply 전에는 소스 트리에 없다(기존 파일에 추가하는 경우 원본으로 복구). apply하면 트리에 쓰고 보관소에서 제거 |
| 사람 확인 `escalations.py` | `<프로젝트>/.cta/escalations/<id>.json` = `Escalation(id, kind, target, category, confidence, evidence, analysis, reason, briefing, tests, run_summary, failed_tests, file_rel, change_line, diff_excerpt, base, commit_message, created_at)`. maintain이 저장·종료(코드 3), resolve가 읽어 재개 후 삭제 |
| 판단 메모 `memos.py` | `<프로젝트>/.cta/memos/*.json` = `Memo(target, category, decision, note, created_at)`. `find_similar(project, target)` 같은 메서드→같은 클래스 최근순 최대 3건. 참고용 |
| 결과 상태 `render.py` | 정상 완료 0 / 사람 확인 필요 3 / 품질 미달 2 / 실패 1 (`EXIT_CODES`) |
| `choose_code_graph` (graph_access.py) | `(project) -> (CodeGraph, 안내 문구, store \| None)` | Neo4j 접속 가능하면 `GraphCodeGraph`(유사 테스트를 그래프에서), 아니면 `ParsingCodeGraph`. store는 호출부가 닫는다 |
| `run_generation` (generate.py) | `(project_path, target, test_class=None, instruction_extra="", model_override=None, warmup_test=None, fast=False, ask_user=None, max_methods=4, include_all=False, regression_sources=None, authorized_tests=None, measure_before=False) -> dict` | generate/maintain/resolve/eval 공용. 기본 테스트 클래스 `<Class>Test`(있으면 메서드 추가) |

## 코드 그래프 (graph/ — M4)

| 항목 | 시그니처 | 계약 |
|---|---|---|
| `GraphNode` | `kind("Class"/"Method"), key, props` | key: 클래스 `Calc`, 메서드 `Calc#add` (오버로드 미구분 — 알려진 한계) |
| `GraphEdge` | `kind, src, dst` | 확정 3종: DECLARES(클래스→메서드), CREATES(메서드→생성 클래스), COVERS(테스트 클래스→실측 실행 메서드) |
| `GraphStore` | `replace_project(project, nodes, edges)` / `neighbors(project, key, edge_kind, direction)` / `methods_by_kind(project, is_test)` | 구현: InMemoryGraphStore(테스트·폴백), Neo4jGraphStore(실물, 환경변수 `CTA_NEO4J_URI/USER/PASSWORD`) |
| `build_graph` (adapters/java) | `(MavenProject) -> (nodes, edges)` | 정적 파싱으로 DECLARES·CREATES. COVERS는 `JacocoCoverageCollector.collect_edges` |
| `parse_covered_methods` | `(jacoco_xml: str) -> set[str]` | 라인 커버>0 메서드 key. 생성자 제외. 커버리지 게이트가 재사용 |

쿼리 6종 중 실응답: `verifying_tests`(COVERS 실측) · `how_to_create`(CREATES, 테스트 우선) ·
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
| `inspect_target` | 대상 조사 | 대상 메서드 식별자(여럿 가능) | 형태·의존·기존 테스트 요약문 |
| `query_code_graph` | 코드 그래프 조회 | 사전 정의 쿼리 종류 + 대상 (자유 쿼리 금지) | 짧은 답 |
| `write_test` | 테스트 쓰기 | 파일 위치 + 코드 | 컴파일·정적 분석 결과 |
| `run_tests` | 테스트 실행 | 실행할 테스트 목록 + 난수 시작값(seed) | 통과/실패 + 실패 내용 |
| `check_quality` | 품질 확인 | 확인할 범위 | 커버리지·뮤테이션 지표 요약 |
| `report_finding` | 한계 보고 | 발견한 문제 | 종료 |
