# architecture.md — 구조와 의존 방향

근거: `docs/02_상세설계_및_개발환경구축_v4.md` 6.1절. 시나리오 정합: ADR-0015.

## 층 구조와 의존 방향

```
cli      ──▶ (모든 층)   # cta 명령 — 조립·입출력만. 판단 로직 없음
tests    ──▶ (모든 층)
adapters ──▶ core, graph # 구체 구현이 포트에 의존, 그래프를 채운다
graph    ──▶ (독립)      # 코드 그래프 모델·저장소·질의 (M4). 언어를 모른다
llm      ──▶ (독립)      # 게이트웨이 호출 전용 통로 (M2)
core     ──▶ (없음)      # 가장 안쪽. 바깥 층 import 금지
```

## 디렉터리 배치

리포 루트는 역할별 5개 폴더로 나뉜다 — 제품 코드는 전부 `cta/` 아래에 있다:

```
cta/        제품 코드 (파이썬 패키지 — core/adapters/llm/graph/sandbox/cli/evals)
tests/      단위·통합 테스트
scripts/    개발용 스크립트 (record_golden, demo_scenarios)
examples/   예제 Maven 프로젝트 (demo = Spring Boot 주문 CRUD, evalbench)
docs/       설계·산출물 문서
```

층 패키지들은 `cta/` 아래에 그대로 있고 import 경로만 `cta.core...` 형태다.
아래 모듈 표의 경로도 `cta/` 생략 표기다(예: `core/ports.py` = `cta/core/ports.py`).
v4 6.1의 목표 구조 중 `mcp_server/`(3단계)만 아직 없다.
어댑터 실물은 `adapters/java/`로 들어간다(M1) — 새 언어 지원 = 폴더 추가.

- **core는 언어를 모른다(R1)**: 언어·빌드 도구 이름 문자열 금지.
  `tests/test_layering.py`가 금지 문자열과 import 방향을 함께 검사한다.
- **LLM 호출은 llm/만 경유(R7)**: record & replay가 작동해야 하므로.

## 명령 ↔ 흐름 (시나리오 기능 이름 기준, ADR-0015 D1)

| 명령 | 시나리오 기능 | 조립 모듈 | 흐름 |
|---|---|---|---|
| `cta generate` | 테스트 생성 기능 | `cli/generate.py` | 재료 수집(materials) → 작성 그래프(core/writer_graph) → 게이트(core/submit) → 제안 |
| `cta maintain` | 변경 대응 기능 | `cli/maintain_cmd.py` | 변경 추출(changes) → 건별 의도 분류(llm/intent) → 검증 테스트 실행 → 규칙표(core/pipeline) → create_test는 generate 경로, escalate/ask는 저장 후 멈춤 |
| `cta resolve` | 판단 전달 기능 | `cli/resolve_cmd.py` | 저장된 사람 확인 항목 → 사람 결정에 따른 지침·허용 목록으로 generate 경로 재개 → 판단 메모 |
| `cta diff` / `apply` / `discard` | 변경 내용 확인 / 반영 | `cli/proposals.py` | 제안 보관소 |
| `cta graph` | 프로젝트 분석 기능 | `cli/graph_cmd.py` | 파싱 + JaCoCo 실측 → Neo4j |

## 모듈 표

| 모듈 | 책임 | 등장 |
|---|---|---|
| `core/__init__.py` | core 층 선언·규칙 안내 | M0 |
| `core/ports.py` | 포트(SourceInspector, TestRunner, …, IntentClassifier, TestLocator)와 데이터 모델 | M0·M5·ADR-0015 |
| `core/textlimit.py` | 도구 반환 문자열 길이 상한(clip) | M0 |
| `adapters/fake.py` | 포트의 인메모리 Fake 구현 — 오프라인 테스트·데모용 | M0 |
| `adapters/java/maven.py` | Maven 프로젝트 탐지 (pom.xml 확인, 표준 경로 계산) | M1 |
| `adapters/java/runner.py` | TestRunner 포트 구현 — 2단계(준비/오프라인 실행) 샌드박스 호출 | M1 |
| `sandbox/docker_sandbox.py` | 범용 Docker 실행 래퍼 — 기본 네트워크 차단, 마운트 통제 | M1 |
| `examples/demo/` | 예제 Spring Boot 주문 CRUD 앱 — 시나리오 SC-001~004의 실험대 | ADR-0015 |
| `llm/__init__.py` | llm 층 선언 — 모든 LLM 호출의 유일한 통로(R7) | M0 |
| `llm/client.py` | 공용 타입(ChatMessage·ChatResponse[usage_tokens])과 LlmClient 포트 | M2 |
| `llm/gateway.py` | 사내 게이트웨이 실호출 클라이언트 (Azure OpenAI 호환, 환경변수로만 설정, usage 수집) | M2 |
| `llm/replay.py` | record & replay 장치 — 재생 실패 시 폴백 없음 | M2 |
| `llm/metering.py` | 호출 수·토큰 합산 래퍼 — "소요 … 토큰" 출력 | ADR-0015 |
| `llm/config.py` | .env 로딩·deployment 선택 — 클라이언트 생성의 유일한 입구 | ADR-0011 |
| `llm/prompts/` | 프롬프트 파일 보관소 (system.md, write_test.md, classify_intent.md) | M0 |
| `llm/generation.py` | 프롬프트 렌더링 + chat → 테스트 코드 (TestCodeGenerator 구현) | M3 |
| `llm/intent.py` | 의도 분류 LLM 구현 — 변경 건별 JSON(분류·확신도·근거·분석), 실패→unclear | M5·ADR-0015 |
| `core/tools/` | 도구 6개 — 1도구 1파일, 문자열 반환 + clip 상한(R4) | M3 |
| `core/writer_graph.py` | 테스트 작성 서브그래프(LangGraph) — 반복(최대 8회)·interrupt·회차 기록 | M3 |
| `adapters/java/inspector.py` | 대상 조사 실물 (클래스 파일 탐색 + 메서드 여럿 확인) | M3 |
| `adapters/java/similar.py` | 파싱 기반 유사 테스트 검색 (그래프 폴백) | M3 |
| `adapters/java/writer.py` | 테스트 쓰기 + 오프라인 컴파일 검사, 테스트 폴더 범위 강제 | M3 |
| `adapters/java/quality.py` | assert 수 비교 검사 최소본 (작성 그래프의 마무리 품질 확인) | M3 |
| `adapters/java/parsing.py` | 시그니처·본문·assert·접근 제어자 파싱 공용 헬퍼 | M3 |
| `adapters/java/materials.py` | 재료 수집 — 메서드 선정, 확인 항목 열거, 객체 생성법 판단, 기존 테스트 파일 | ADR-0015 |
| `adapters/java/failures.py` | 실행 출력 해석 — 실패 테스트(기대·실제), 컴파일 오류 수, 회차 요약 | ADR-0015 |
| `adapters/java/assert_report.py` | assert 전/후 비교 보고 — 테스트 메서드 단위, 엄격함 점수 | ADR-0015 |
| `adapters/java/regression.py` | 게이트 ⑥ — 수정 전 코드에서 실패하는지 확인(파일 교체·복구) | ADR-0015 |
| `evals/golden_case.py` | 대표 검증 시나리오 배선 단일 정의 (기록 생성·재생 공유) | M3 |
| `graph/model.py` | 그래프 노드·엣지 모델 (확정 엣지 3종) | M4 |
| `graph/store.py` | GraphStore 인터페이스 + 인메모리 구현 | M4 |
| `graph/neo4j_store.py` | Neo4j 실물 저장소 (샌드박스 밖 별도 컨테이너, v4 6.5) | M4 |
| `graph/answers.py` | 그래프 질의 → 답 문장 (CodeGraph 구현) | M4 |
| `adapters/java/graph_builder.py` | Java 소스 → 노드·엣지 (DECLARES·CREATES) | M4 |
| `adapters/java/coverage.py` | JaCoCo 실측 실행·파싱 — COVERS 근거, 커버리지 게이트 재사용 | M4 |
| `core/pipeline/models.py` | 파이프라인 데이터 모델 (변경 심볼·변경 묶음·의도·조치) | M5 |
| `core/pipeline/decide.py` | 조치 결정 규칙표(+trivial 행) + 지침서 조립 — LLM 금지(R2) | M5 |
| `core/pipeline/maintain.py` | 변경 대응 분석 — 건별 분류→검증 테스트 실행→규칙표 (포트만 사용) | ADR-0015 |
| `adapters/java/changes.py` | git diff → 변경 심볼 + 단서(시그니처·접근 제어자·주석만·커밋 메시지·이슈), 수정 전 소스, 참조 파싱 TestLocator | M5·ADR-0015 |
| `core/gates.py` | 게이트 실행기·설정(cta.toml [gates]) — 검문소의 언어 무관 틀 | M6 |
| `core/config.py` | cta.toml 전체 설정 — 게이트·반복 상한·시간 초과·모델·토큰 예산. 우선순위 환경변수 > .env > cta.toml | 3단계 A-2 |
| `llm/masking.py` | 시크릿 가림 — 키 값·키 모양을 `****`로, CLI 출력 직전 2차 방어 | 3단계 A-3 |
| `cli/hints.py` | 오류 안내 표 — 예외·문구 → "왜 / 할 일 / 명령" 세 줄. `main()`의 유일한 예외 출구 | 3단계 A-5 |
| `.github/workflows/ci.yml` | CI — check(ruff·pytest 재생 모드, py 3.11/3.12) + integration(수동: docker·neo4j) | 3단계 A-1 |
| `core/submit.py` | 생성→게이트 재시도 루프 (탈락 사유 반환, 소진 시 사람 확인) | M6 |
| `adapters/java/gates.py` | 게이트 ①assert(메서드 단위·허용 목록) ②스킵 ③범위 ④커버리지 구현 + 기준선 스냅샷 | M6 |
| `adapters/java/mutation.py` | 게이트 ⑤ PIT 뮤테이션 (overlay pom, 메서드 집합 집계, 전후 비교용 측정) | M6 |
| `cli/main.py` | `cta` 진입점 — generate/maintain/resolve/diff/apply/discard/graph/eval/demo | CLI화 |
| `cli/render.py` | 화면 출력 형식 — 시나리오 기대 출력(①② 판단 블록, 상자, 결과 상태·종료 코드) | ADR-0015 |
| `cli/proposals.py` | 제안 보관소 — 생성물은 apply 전까지 소스에 반영 안 됨(v4 Step 3) | CLI화 |
| `cli/escalations.py` | 사람 확인 보관소 — 저장하고 멈춤, resolve가 재개 | ADR-0015 |
| `cli/memos.py` | 판단 메모 — resolve 결정 기록, 다음 maintain의 참고 자료(키워드 검색) | ADR-0015 |
| `cli/graph_access.py` | 코드 그래프 접속 선택 — Neo4j 접속 확인 후 실물, 아니면 파싱 폴백 (generate·maintain 공용) | ADR-0015 |
| `cli/generate.py` | 재료 수집→생성→게이트→제안 조립 + 4단계 출력 | CLI화·ADR-0015 |
| `cli/maintain_cmd.py` | 변경 대응 조립 + 판단 블록 출력 + 사람 확인 상자 | ADR-0015 |
| `cli/resolve_cmd.py` | 판단 전달 — 사람 결정에 따른 지침·허용 목록으로 재개 | ADR-0015 |
| `cli/file_mode.py` | `cta generate <파일명>` 파일 탐색·프로젝트 인식 | 사용성 |
| `cli/locate.py` | 프로젝트 자동 인식(현재 폴더→상위→하위) — 전 명령의 --project 생략 지원 | 사용성 |
| `cli/graph_cmd.py`·`eval_cmd.py`·`demo_cmd.py` | graph/eval/demo 서브커맨드 | CLI화 |
| `scripts/record_golden.py` | 대표 시나리오의 LLM 호출 기록 생성 스크립트 (대본/실호출) | M3 |
| `scripts/demo_scenarios.py` | SC-002/SC-003 재현용 임시 저장소 생성 (버그 수정 커밋 / 리팩터링 커밋) | ADR-0015 |
| `scripts/render_capture.py` · `render_diagram.py` | 산출물 이미지 재생성 — 실행 로그 → 터미널 모양 PNG / mermaid → PNG(로컬 Chrome 헤드리스) | 산출물 |

## 구조 결정 (v4 원문 대조 완료 — 충돌 없음)

1. **src 레이아웃 대신 최상위 패키지** `core/ adapters/ llm/` — CLAUDE.md의 층 표기와
   디렉터리가 1:1로 일치해 test_layering 검사와 독자의 머릿속 지도가 단순해진다.
2. **포트는 Protocol** — Fake·실물 어댑터가 상속 없이 구조적으로 들어맞는다.
3. **빈 selector 거부는 어댑터 책임** — R5 원문("어댑터가 빈 selector를 거부한다") 그대로.
   공통 계약이므로 어댑터 테스트가 반드시 검증한다.
4. **사람 개입의 재개 지점은 JSON 상태**(ADR-0015 D3) — LangGraph 체크포인트를 디스크에 두는
   대신 결정 단계 이후의 상태를 `.cta/escalations/`에 저장하고 resolve가 이어 간다.
   재개 지점이 "테스트 작성 단계 진입"으로 고정돼 있어 의존성을 늘리지 않고도 충분하다.
