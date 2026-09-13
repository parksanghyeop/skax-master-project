# Code Test Agent (`cta`) — E2E 서비스 개발 산출물

PoC(1단계)·테스트 및 고도화(2단계)에서 만든 에이전트를 남이 설치해 돌릴 수 있는 제품으로 닫는 단계.
구성은 PoC구현.md와 동일(한눈에 보기 → 계약 → 구현 → 문제 해결 → 검증 로그 원문 → 구현 범위 3구역).
2026-09-13 기준. 09-06 판에서 "[측정 대기]"였던 수치는 실제 게이트웨이(gpt-5)로 측정해 채움.

## 한눈에 보기

- **이번 단계에서 구현한 것**: CI(replay 모드) · `cta.toml` 단일 설정 · 시크릿 3 테스트 · `--quiet` + exit code CI 사용법 · 오류 안내 "왜/할 일/명령" 10상황 ·
  **Skill**(SKILL.md 2종, 규칙 선택, ADR-0017) · 결함 세트 v2(12건) + 자기 검사 · 판단 메모 불변식 · **로컬 실행 기본**(ADR-0022) ·
  **Deep Agent 엔진**(메인 test-lead + 서브 3, 하네스 미들웨어, ADR-0024·0025) · **GraphRAG 영향 범위**(CALLS 엣지, `--impact`, ADR-0026) ·
  **판단 메모 임베딩 검색**(하이브리드, ADR-0026) · LLM 비용 절감(ADR-0023) · 제품 README · 최종산출물 폴더
- **검증한 것**: 단위 테스트 314건 · 결함 세트 검출률 83.3%(12건 실호출) · 의도 세트 정확도 100%(10건 실호출) ·
  실사용 시나리오 6종(generate / maintain / `--impact` / escalate → resolve / 메모 검색 / demo) 실제 게이트웨이·Maven으로 완주
- **발견한 것**: 실사용 점검에서 버그 7건 — 콘솔 인코딩, 커버리지 탈락 사유 부족, 조각 들여쓰기, 제안 덮어쓰기, 토큰 합산 누락,
  `resolve --intended` 병합 실패(SC-003 핵심 경로), 재개 실패 시 항목 유실. 전부 수정·테스트 추가
- **미측정**: `--runner docker`, `cta graph`(Neo4j 적재) — 이 PC에 Docker·Neo4j 없음
- 구현 범위 3구역은 [§6](#6-구현-범위--동작-확인-완료--미검증--향후-확장), 계약 변경분은 [§2](#2-이번-단계의-계약-변경분)

| 항목 | 값 |
|---|---|
| 기간 | 2026-09-06 ~ 09-13 |
| 커밋 | 09-07 이후 26개, 전부 main에 push (마지막 `3cbac77`) |
| 테스트 | 단위 314건 · Docker 통합 3건 · Neo4j 통합 1건 · 결함 세트 자기 검사 12건 |
| 새 모듈 | `core/agent/`(build·subagents·limits·tools·prompts) · `llm/chat_model.py`·`model_cassette.py`·`embeddings.py` · `adapters/java/calls.py` · `graph/impact.py` · `core/config.py` · `llm/masking.py` · `cli/hints.py` · `adapters/java/skills/` · `sandbox/local_sandbox.py`·`factory.py` |
| 새 ADR | 0016 대화 압축 불필요(→0024로 폐기) · 0017 Skill · 0019/0022 로컬 실행 · 0020 unclear 축소 · 0023 LLM 비용 · 0024 Deep Agents · 0025 툴 재정의 · 0026 영향 범위·임베딩 |

---

**전체 구조** — LLM은 의도 판단·테스트 작성 두 곳. 가드레일은 전부 일반 코드

![Agent Architecture](1-agent-architecture.png)

## 1. 목표와 판정

- 3단계 목표: 개발자(작성자 아닌 사람)가 설치 가이드만 보고 자기 Maven 프로젝트에 돌릴 수 있는 상태
- 2단계 관문 3항목(게이트 불변식·베이스라인 수치·escalate → resolve 실연) 통과 후 진입
- 원칙은 "넓히지 않고 닫는다". 예외 3건은 멘토 피드백에 따른 기술 어필: Skill(ADR-0017), Deep Agent 전환(ADR-0024), GraphRAG 영향 범위·임베딩(ADR-0026)
- 판정: 실호출·Maven 환경에서 전 시나리오 완주. Docker·Neo4j 경로만 미측정

## 2. 이번 단계의 계약 변경분

PoC구현.md §2.0 계약에 더해진 것만 기재. 전체는 `docs/contracts.md`.

| 계약 | 핵심 필드 | 만드는 곳 → 쓰는 곳 | 정의 파일 |
|---|---|---|---|
| `CtaConfig` | `gates`, `retry(ask_every=4, max_total=8)`, `gateway_timeout_sec`, `model`, `reasoning_effort`, `max_tokens_per_run`, `impact_max_callers=3` | `cta.toml` → `run_generation`·`run_maintain`. 우선순위 환경변수 > .env > cta.toml > 기본값 | `core/config.py` |
| `Skill` / `SkillSignals` | `name, description, when, body` / `uses_mock, regression, resume_with_authorized` | 재료 수집·실행 종류 → 규칙 테이블 → `PromptedGenerator.style_notes` | `adapters/java/skills/select.py` |
| `Hint` | `why, todo, command` | 예외·오류 문구 → 화면 3줄 | `cli/hints.py` |
| `AgentPorts` | 툴 6개 뒷단 포트 + `ask_user` + `llm_middleware` | `cli/generate.py` → `build_agent` | `core/agent/ports.py` |
| `RunLedger` | `attempts, ask_every, max_total, last_failure` | `wrap_tool_call`로 `run_tests` 집계 → 툴 결과에 안내 첨부 | `core/agent/limits.py` |
| 호출 기록 v2 (`ModelRequest` 키) | deployment + 시스템 프롬프트 + 정규화 메시지(역할·내용·tool_calls) + 툴 이름 | `RecordingModelMiddleware` → `ReplayModelMiddleware`, 완전 일치만 | `llm/model_cassette.py` |
| `GraphEdge` | `kind, src, dst, confidence="", excerpt=""` — CALLS만 confidence(high/medium)·excerpt 필수 | `adapters/java/calls.py` → `GraphStore.edges_in` | `graph/model.py` |
| `Caller` / `ImpactFinder` | `target, confidence, excerpt` / `find(target) -> list[Caller]` | `GraphImpactFinder`·`StaticImpactFinder` → `analyze_changes` 지침서·파생 건. 규칙 테이블 미반영 | `core/pipeline/models.py`, `core/ports.py` |
| `EmbeddingClient` | `embed(texts, model) -> list[list[float]]` | `make_embedding_client()`(미설정 시 None) → `resolve` 저장·`maintain` 검색 | `llm/embeddings.py` |
| `Memo` | `target, category, decision, note, created_at, situation="", embedding=None` | `resolve` → `.cta/memos/*.json` → `find_similar(project, target, query_vector)` | `cli/memos.py` |
| `pending_proposal_code` | 같은 테스트 클래스·경로의 대기 제안 코드 | `run_generation`이 "기존 파일"로 삼아 이어서 생성 | `cli/proposals.py` |
| `MeteredClient(max_tokens)` | 누적 토큰 상한 초과 시 `BudgetExceededError` | `run_generation` → 생성물 되돌림 + 안내 | `llm/metering.py` |

---

## 3. 핵심 구현 내용

**패키지 구조** — `cli → core ← adapters/java · graph · llm · sandbox`

![Project Structure](6-project-structure.png)

### 3.1 마감 — 남이 돌릴 수 있게 (M8-a)

**명령별 흐름과 exit code** — CI는 exit code로 분기

![CLI Flows](5-cli-flows-infographic.png)

- **CI** `.github/workflows/ci.yml`: `check`(Python 3.11/3.12 · ruff · `pytest -q` replay 모드 · 결함 세트 자기 검사) 모든 push, `integration`(Docker·Neo4j 서비스 컨테이너) 수동. 게이트웨이 키 없이 실행. 실호출 시도 시 실패가 정상(R7)
- **설정 파일** `cta.toml` 절 6개(`[gates] [retry] [gateway] [llm] [budget] [impact]`). 시크릿 미수용. cta.toml 값은 환경변수 기본값 자리에만 배치
- **시크릿**: `docker run` 인자 조립을 순수 함수로 분리, `-e`류 옵션 부재를 테스트로 고정. 출력 직전 마스킹. 호출 기록에 키 없음. 키 없으면 클라이언트 생성 시점에 실패
- **오류 안내**: 예외 → 표 10행 → "오류: 원인 / 왜 / 할 일 / 명령". `main()`이 유일한 출구, `CTA_DEBUG=1`이면 전체 traceback. Windows cp949 콘솔 대응으로 진입점에서 stdout/stderr UTF-8 재설정(09-13 수정)
- **CI 사용법**: exit code 0/3/2/1 의미와 GitHub Actions 예시. `--quiet`로 진행 줄 생략

### 3.2 확장 — 기술 어필 (M8-b)

**Skill (ADR-0017)**

- `adapters/java/skills/<이름>/SKILL.md` 2개: `junit5-mockito`(strict stubs, matcher 혼용 금지, 값 객체 직접 생성), `regression-test`(경계 입력 추출, 정확한 기대값, 기존 메서드 수정 금지)
- 선택은 규칙 테이블. 신호는 재료 수집의 mock 판정, 회귀 게이트 부착, resolve 재개 등 이미 결정된 값만 사용(LLM 없음 → replay 가능)
- 툴 6개 유지(R4), core 무변경(R1). 화면 `[2/4] 적용 스킬: …`이 선택 로그. 스킬 본문에 스킵 유도 문구 없음을 테스트로 고정

**Deep Agent 엔진 (ADR-0024·0025)**

- `--engine deep`: `create_deep_agent()`로 메인 test-lead + 서브 explorer(읽기)·writer(쓰기·실행)·diagnoser(읽기) 조립. 메인은 `write_todos`·`task`로 계획·위임, 종료는 `check_quality` 또는 `report_finding`으로 고정
- 하네스 미들웨어: `FilesystemPermission(write deny)` + `HideWriteTools`(내장 쓰기 툴 차단·숨김), `RunLedger`(`wrap_tool_call`로 `run_tests` 집계 — 시도 ≤ 8, 4회마다 사용자 확인, 같은 실패 2회 시 diagnoser), `recursion_limit=400`, `TodoListMiddleware`, `RecordingModelMiddleware`/`ReplayModelMiddleware`(호출 기록 v2), `MeteringModelMiddleware`
- R4 재정의(ADR-0025): 고유 툴 6개 + 하네스 내장 툴(읽기·계획·위임) 허용, 내장 쓰기 툴 deny, 사람 개입 툴 `ask_user`(메인만)
- legacy(LangGraph 서브그래프)와 같은 `run_writer(state)` 계약. 게이트 루프(`core/submit.py`)·화면 출력 공유. 기본값은 아직 legacy

**GraphRAG — 영향 범위 (ADR-0026 D1·D2)**

![Graph DB Architecture](4-graphdb-architecture.png)

- 요청은 "임베딩 벡터 유사도로 수정 메서드의 영향 범위 찾기". 검토 결과 코사인 유사도는 닮은 코드를 찾을 뿐 호출 관계를 못 찾음. v4 4.1도 코드 검색에 임베딩 미사용으로 명시 → 코드 그래프 CALLS 엣지로 결정
- CALLS 추출(`adapters/java/calls.py`): 같은 클래스 호출·선언 타입이 프로젝트 클래스인 호출 → high, 타입 미상이나 메서드명 유일 → medium, 그 외 엣지 생성 안 함. 생성자·재귀·주석·문자열 제외. main 트리만(테스트 → 코드는 COVERS 담당)
- 쓰임: `maintain` 출력 "영향 범위" 행, 지침서에 호출자·호출 줄·"호출자 경유 시나리오" 지침, `--impact`로 확신 high 호출자에 파생 생성(깊이 1, `[impact] max_callers` 기본 3). 규칙 테이블·기존 테스트 상태 판정에는 미반영 — COVERS가 이미 간접 실행을 실측
- `callers` 쿼리 실응답("정적 추정" 표기 필수). Neo4j 없으면 그 자리 파싱 폴백

**판단 메모 임베딩 검색 (ADR-0026 D3)**

- `llm/embeddings.py`: 게이트웨이 `/embeddings`(`text-embedding-3-small`), `RecordingEmbeddingClient`/`ReplayEmbeddingClient`((모델, 글) → 벡터, 없는 글은 실패), 순수 Python 코사인. 새 의존성 0
- `resolve` 시 상황 요약(커밋 메시지 첫 줄 + 대상 + 분석, 자연어만)을 임베딩해 메모에 저장. `maintain`은 이름 일치 → 코사인 ≥ 0.35 순으로 최대 3건 첨부. 게이트웨이 미설정 시 이름 일치만
- 불변식 유지: 메모 내용과 무관하게 `decide()` 결과 동일

**LLM 비용 (ADR-0023)**

- 기존 테스트 파일에 추가 시 새 멤버 조각만 출력 → `merge.py`가 병합. 추론 강도 기본 low. 토큰 내역(입력·출력·추론·캐시) 기록
- 09-13 병합기 보강: 같은 이름 메서드는 어노테이션까지 제자리 교체(`resolve --intended` 경로), 공통 들여쓰기 정규화, 같은 클래스의 대기 제안 위에 이어서 생성

### 3.2b 로컬 실행 — 기본 실행 장치 (ADR-0019 → ADR-0022)

- Docker 준비 단계(첫 실행 5분)·실행마다 수십 초가 반복 개발의 최대 비용. 원인은 Windows 바인드 마운트
- 이 PC의 Maven·JDK를 기본 실행 장치로, Docker는 `--runner docker`. `--fast`는 커버리지·뮤테이션 게이트 생략만
- `LocalSandbox`는 `DockerSandbox`와 같은 `run()` 시그니처. 컨테이너 경로 → 호스트 경로 변환, `-o`·`-Dmaven.repo.local=` 제거
- 실측(이 PC): 기존 테스트 실행 6초, 컴파일 검사 2초, JaCoCo 9.5초, PIT 30초. 빈 selector 거부(R5) 유지
- 대가: 기본 실행에 격리 없음. 화면 안내 1줄, 타인 코드·CI는 `--runner docker` 권고

### 3.3 릴리스 (M8-c)

- 제품 README(5분 시작·명령 요약·문서 지도·한계), 개발 킷은 `docs/개발환경.md`. 사용가이드 §13 CI · §14 지원 범위와 한계
- 09-13 실사용 점검: 실제 게이트웨이 키·Maven 3.9.16으로 전 명령 실행. 버그 7건 수정(§4), 평가 하네스 실측(§5)
- `최종산출물/` 신설: 그림 6장(`cta-diagrams.drawio`), 최종보고, 본 문서. 과거 `docs/` 문서는 동결

---

## 4. 주요 문제 해결 및 기술 리서치

| 이슈 구분 | 문제 상황 및 원인 | 리서치 및 해결 과정 |
|---|---|---|
| **결함** | `resolve --intended`가 8회 전부 실패. append 병합이 수정 메서드를 파일 끝에 덧붙여 `method already defined` 컴파일 오류, 안 붙이면 기존 그대로라 assert 실패 — 둘을 번갈아 반복. 단위 테스트에 "기존 메서드 수정" 케이스 없음 | • **발견:** SC-003 실호출 <br>• **적용:** `merge.py`가 조각의 메서드명이 기존과 같으면 어노테이션·주석까지 제자리 교체. 순서 유지 테스트 추가 → 2회차 통과 |
| **결함** | 같은 테스트 클래스를 겨냥한 생성이 한 실행에 여럿(`--impact` 파생 3건)이면 뒤 제안이 앞 제안을 덮어써 테스트 유실 | • **발견:** `cta diff`에서 제안 1건만 남음 <br>• **적용:** `pending_proposal_code`로 대기 제안을 "기존 파일"로 삼아 이어서 생성, 결과가 제안 대체. 소스 트리 복구는 디스크 원문 기준 |
| **결함** | 커버리지 게이트가 3회 재생성 내내 같은 줄(88·89)로 탈락. 사유에 줄 번호만 있어 모델이 빠진 경로를 모름 | • **적용:** `describe_source_lines`로 미실행 줄 소스 원문 첨부 + "위 줄이 실행되는 입력을 시험하라". 재실행 시 1회 통과, 커버리지 100/100 |
| **결함** | Windows cp949 콘솔에서 `cta --help`부터 `UnicodeEncodeError` | • **적용:** `main()` 진입에서 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` |
| **결함** | 재개가 not_passed로 끝나도 escalation 항목 삭제 → 사람 결정 유실 / 조각 첫 줄만 들여쓰기 없으면 본문 8칸 / maintain "소요 토큰"이 분류 호출만 집계 | • **적용:** 제안 미생성 시 항목 유지·`--hint` 안내 / 공통 들여쓰기 정규화 / 분류 + 생성 합산 |
| **설계** | RAG·임베딩으로 영향 범위를 찾자는 요청이 v4 4.1(코드 검색에 임베딩 미사용)과 충돌 | • **리서치:** 코사인 유사도는 "닮은 코드"를 찾을 뿐 호출 관계 아님. 상속·DI·리플렉션으로 static analysis도 100% 불가 <br>• **적용:** ADR-0026 — CALLS 엣지(confidence 부착, 규칙 테이블 미반영) + 임베딩은 판단 메모(자연어)에만 |
| **설계** | Deep Agents 하네스 내장 툴(`write_file`, `edit_file`, `task`, `write_todos`)이 R4 "툴 6개"와 충돌 | • **적용:** ADR-0025로 R4 재정의 — 고유 툴 6개 + 하네스 계획·위임·읽기 툴 허용, 쓰기 툴은 `FilesystemPermission` deny + `HideWriteTools` 두 겹 차단 |
| **결함** | 판단 메모 두 건 연속 저장 시 한 건 유실 — 파일명 마이크로초 타임스탬프가 Windows 시계 해상도(~15ms) 안에서 중복 | • **적용:** 같은 자리 수 순번(`-00`, `-01`) 부여, 정렬 순서 유지. `datetime` 고정 회귀 테스트 |
| **벤치마크** | 2단계 미검출 1건(truncate-boundary)이 `<=` → `<`가 길이==max에서 같은 결과를 내는 동치 변이 | • **리서치:** equivalent mutant <br>• **적용:** 케이스마다 `probe`/`expected`, `check_defects.py`로 버그/고친 버전 비교 자기 검사. 관찰 가능한 결함으로 교체 |
| **설계** | 설정 우선순위 — 커밋되는 `cta.toml`이 개인 `.env`를 덮으면 안 됨 | • **적용:** cta.toml 값은 `make_llm_client(model_default, timeout_default)` 인자로만 전달 → 환경변수 > .env > cta.toml > 기본값 |
| **재생** | 스킬·프롬프트 변경 시 저장된 호출 기록 재생 실패 위험 | • **확인:** `cta demo`는 자체 `STYLE_NOTES`로 생성기 구성 → 영향 없음. 09-13 깨끗한 트리에서 재생 성공 확인 |

---

## 5. 핵심 동작 검증

이 PC(Windows, Python 3.12 venv, JDK 23, Maven 3.9.16, 사내 게이트웨이 gpt-5, Docker·Neo4j 없음)에서 실제로 돌린 것만 기재.

| 검증 | 내용 | 결과 |
|---|---|---|
| 1 | `ruff check .` · `ruff format --check .` | 통과 |
| 2 | `pytest -q` (replay 모드) | **314 passed**, 4 deselected(docker·neo4j) |
| 3 | `python scripts/check_defects.py` — 결함 12건 컴파일 + probe 비교 | 12/12 통과 |
| 4 | `cta generate --class …OrderService --max-methods 1` (실호출, 게이트 전부) | 1회 시도, 테스트 2개, 커버리지 100/100, PIT 2/2, 35초 · 4,655 토큰 |
| 5 | `cta maintain --message "fix: …"` (SC-002, 임계값 `>` → `>=`) | 회귀 테스트 3개, 회귀 게이트 "수정 전 코드에서 실패함" 통과, 뮤테이션 90% 유지 |
| 6 | `cta maintain --impact` (`findById` null 방어) | 원본 + 파생 3건(`OrderController#get`, `pay`, `cancel`) 게이트 통과, `OrderControllerTest.java` 신규 |
| 7 | `cta maintain` (SC-003, 리팩터링 중 `setScale` 변경) → `cta resolve --intended` | 4건 중 2건 실패 검출 후 exit 3 → 2회차 통과, 기대값 `1500` → `1500.00`, 허용 2건 외 assert 27개 보존 |
| 8 | 다음 `cta maintain --plan-only` | "판단 메모 검색: 이름 일치 + 상황 임베딩(text-embedding-3-small)", 타 클래스 메모 참고 첨부 |
| 9 | `cta demo` (깨끗한 트리) | 저장 기록 재생, exit 0 |
| 10 | `cta eval --intents --variant with` (실호출) | 정확도 100%, 잘못된 unclear 0건, 8,726 토큰 |
| 11 | `cta eval --fast` (결함 세트 12건, 실호출) | 12건 수용, 10건 검출(83.3%), escalation 0, 평균 시도 1.0회, 252초 |

**[검증 4 — generate 품질 확인]** 실행 로그 원문:

```text
  [4/4] 품질 확인
        확인 항목 충족   2 / 2  (100%)
        버그 검출력      100%
        기준 낮춤 여부   없음
        게이트[assert] 통과 — 기존 assert 27개 모두 보존됨
        게이트[skip] 통과 — 새 스킵 어노테이션 없음
        게이트[scope] 통과 — 변경이 허용 목록(1개) 안에 있음
        게이트[coverage] 통과 — 라인 100%, 분기 100% (기준 충족)
        게이트[mutation] 통과 — 심은 버그 2개 중 2개 검출(100%)

  수정됨      src/test/java/com/example/demo/order/OrderServiceTest.java  (+2 테스트, 제안 'OrderServiceTest')
  테스트   22개 / 전체 통과
  소요     35초 · 4,655 토큰 (입력 4,033 · 출력 622 · 추론 512 · 캐시 3,968)

  결과 상태: 정상 완료
```

**[검증 6 — `--impact` 영향 범위]** 실행 로그 발췌:

```text
  영향 범위(정적 추정): 호출자에도 생성 (--impact, 상한 3건)
  ① OrderService.findById
     영향 범위     OrderController.get [high], OrderService.cancel [high], OrderService.pay [high], OrderService.updateAmount [high]  (정적 추정)
  ② OrderController.get  ↳ 영향 범위 (OrderService.findById 변경의 호출자)
  ③ OrderService.cancel  ↳ 영향 범위 (OrderService.findById 변경의 호출자)
  ④ OrderService.pay  ↳ 영향 범위 (OrderService.findById 변경의 호출자)
  …
  수정됨       OrderServiceTest.java (+3)  → 제안 'OrderServiceTest': cta diff / cta apply
  수정됨       OrderControllerTest.java (+2)  → 제안 'OrderControllerTest': cta diff / cta apply
```

**[검증 7 — SC-003 사람 확인 상자]** 실행 로그 원문:

```text
  영향 테스트 실행 → 4건 중 2건 실패

  ┌────────────────────────────────────────────────────┐
  │  사람 확인 필요 — 자동으로 고치지 않았습니다       │
  └────────────────────────────────────────────────────┘

   동작이 안 바뀌어야 하는 변경인데 테스트가 깨졌습니다.

     (A) 이번 수정에 진짜 버그가 있다          ← 가능성 높음
     (B) 테스트가 내부 구현에 너무 붙어 있다

   실패한 테스트
     · calculate_multipleItems_sumsBeforeRate   기대 2500, 실제 2500.00
     · calculate_singleItem_appliesRate         기대 1500, 실제 1500.00

   확인해 보실 곳
     PricingCalculator.java 27행 부근
       바뀌기 전 : return subtotal.multiply(rate).setScale(10, RoundingMode.HALF_DOWN);
       바뀐 후   : BigDecimal total = subtotal.multiply(rate);
                   return total.setScale(2, RoundingMode.HALF_DOWN);

   수정한 테스트   0건 (일부러 안 함)
   사람 확인 필요  1건
```

**[검증 10·11 — 평가 하네스]** 실행 로그 원문:

```text
===== 의도 세트 요약 =====
  all: {'runs': 10, 'accuracy': 1.0, 'unclear_rate': 0.1, 'avg_elapsed_s': 4.8}
  false_unclear: 0
  total_tokens: 8726

===== 평가 요약 =====
  cases: 12
  accepted: 12
  detected: 10
  detection_rate: 0.833
  escalation_rate: 0.0
  avg_writer_attempts: 1.0
  total_elapsed_s: 251.6
```

기록: `cta/evals/results/intents-local-intents-v1-gpt-5-20260913-022245.json`, `eval-local-defects-v2-gpt-5-20260913-022701.json`

---

## 6. 구현 범위 — 동작 확인 완료 / 미검증 / 향후 확장

**동작 확인 완료** (이 PC에서 실행 결과로 확인)

| 항목 | 근거 |
|---|---|
| `cta.toml` 설정 6절, 우선순위, 반복 상한, 토큰 예산, `[impact]` | `tests/test_config.py`, `test_writer_graph.py::TestConfigurableLimits`, `test_secrets.py::TestTokenBudget` |
| 시크릿 3 테스트, 출력 마스킹 | `test_llm_config.py`, `test_secrets.py` |
| 오류 안내 10상황, `CTA_DEBUG`, UTF-8 콘솔 | `tests/test_hints.py`, CLI 스모크 |
| Skill 읽기·규칙 선택·렌더링·불변식 | `tests/test_skills.py` |
| Deep Agent 조립·위임·원장 상한·쓰기 차단·호출 기록 v2 | `tests/test_agent_deep.py`, `test_model_cassette.py`, `test_chat_model.py` |
| CALLS 추출 확신도 규칙, `callers` 답, 폴백, 데모 실측 4곳 | `tests/test_calls.py`, `test_graph.py` |
| 영향 범위 불변식(`decide` kind·reason 불변), `--impact` 파생 건 규칙 | `tests/test_maintain_core.py::TestImpactRange` |
| 임베딩 게이트웨이 순수 함수·기록/재생·하이브리드 검색·구 메모 호환 | `tests/test_embeddings.py` |
| 병합기: 같은 이름 제자리 교체, 들여쓰기 정규화, 대기 제안 이어붙임 | `test_java_adapter.py::TestMergeReplacesSameNameMethods` 등, `test_proposals.py` |
| 커버리지 탈락 사유 줄 원문 | `tests/test_coverage_describe.py` |
| 결함 세트 12건 컴파일·관찰 가능 | 검증 3 |
| 판단 메모 불변식, 프롬프트 비누적, memos 덮어쓰기 수정 | `test_maintain_core.py::TestMemosCannotBypassRules`, `test_writer_graph.py::TestPromptDoesNotAccumulate`, `test_escalation_flow.py` |
| 실호출 시나리오 6종, 평가 하네스 2종 | 검증 4~11 |

**구현됐지만 미검증** (Docker·Neo4j 필요)

| 항목 | 남은 확인 |
|---|---|
| `--runner docker` 격리 실행 | Docker 환경에서 준비 단계 + 실행 |
| `cta graph --coverage` Neo4j 적재, `verifying_tests` 실측 경로 | Neo4j 컨테이너에서 빌드 후 `maintain` |
| CI `integration` 잡 | GitHub Actions 수동 실행 |
| `--engine deep` 결함 세트 수치 | legacy와 비교 후 기본값 결정 |

**향후 확장 예정**

| 항목 | 왜 |
|---|---|
| `--impact` 전/후 검출률 비교 | 호출자 경유 테스트의 효과 수치화 |
| 임베딩 유사도 기준치(0.35) 보정 | 메모 누적 후 실사용 데이터로 |
| 스킬 추가(`boundary-values`·`spring-slice-test`) | 전/후 수치 확인 후 |
| 깊이 2 이상 전이 영향, 메서드 단위 COVERS | 비용 대비 효과 측정 후 |
| 멀티모듈 Maven·Gradle, tree-sitter 파서 | 3단계 범위 밖 |

---

## 7. 문서 지도 · 재현 명령

| 문서 | 내용 |
|---|---|
| `최종산출물/최종보고.md` | 프로젝트 전체 최종 보고 |
| `최종산출물/cta-diagrams.drawio` + PNG 6장 | Agent 구조 · 상세 아키텍처 · 명령별 흐름 · Graph DB · CLI 흐름(간소화) · 프로젝트 트리 |
| `docs/adr/ADR-0017 · 0022 · 0023 · 0024 · 0025 · 0026` | Skill · 로컬 실행 · LLM 비용 · Deep Agents · 툴 재정의 · 영향 범위·임베딩 |
| `docs/contracts.md`, `docs/architecture.md` | 데이터 모델·시그니처, 모듈 표 |
| `docs/사용가이드.md` §9·§13·§14 | cta.toml · CI · 지원 범위와 한계 |

```
pytest -q                                 # 단위 314건 (Docker·Neo4j 제외)
python scripts/check_defects.py           # 결함 세트 자기 검사 (JDK 17+)
cta eval --intents --variant with         # 의도 세트 정확도 (게이트웨이 필요)
cta eval --fast                           # 결함 세트 검출률 (게이트웨이·Maven 필요)
cta maintain --diff HEAD~1 --impact       # 영향 범위 파생 생성
python scripts/render_final_diagrams.py 최종산출물/cta-diagrams.drawio   # 그림 재생성
```
