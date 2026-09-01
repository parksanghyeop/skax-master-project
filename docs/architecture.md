# architecture.md — 구조와 의존 방향

근거: `docs/02_상세설계_및_개발환경구축_v4.md` 6.1절.

## 층 구조와 의존 방향

```
cli      ──▶ (모든 층)   # cta 명령 — 조립·입출력만. 판단 로직 없음
tests    ──▶ (모든 층)
adapters ──▶ core, graph # 구체 구현이 포트에 의존, 그래프를 채운다
graph    ──▶ (독립)      # 코드 그래프 모델·저장소·질의 (M4). 언어를 모른다
llm      ──▶ (독립)      # 게이트웨이 호출 전용 통로 (M2)
core     ──▶ (없음)      # 가장 안쪽. 바깥 층 import 금지
```

v4 6.1의 전체 목표 구조 중 `sandbox/`(M1), `cli/`·`mcp_server/`(3단계)는 아직 없다.
어댑터 실물은 `adapters/java/`로 들어간다(M1) — 새 언어 지원 = 폴더 추가.

- **core는 언어를 모른다(R1)**: 언어·빌드 도구 이름 문자열 금지.
  `tests/test_layering.py`가 금지 문자열과 import 방향을 함께 검사한다.
- **LLM 호출은 llm/만 경유(R7)**: record & replay가 작동해야 하므로.

## 모듈 표

| 모듈 | 책임 | 등장 마일스톤 |
|---|---|---|
| `core/__init__.py` | core 층 선언·규칙 안내 | M0 |
| `core/ports.py` | 포트(SourceInspector, TestRunner)와 데이터 모델 | M0 |
| `core/textlimit.py` | 도구 반환 문자열 길이 상한(clip) | M0 |
| `adapters/fake.py` | 포트의 인메모리 Fake 구현 — 오프라인 테스트·데모용 | M0 |
| `adapters/java/maven.py` | Maven 프로젝트 탐지 (pom.xml 확인, 표준 경로 계산) | M1 |
| `adapters/java/runner.py` | TestRunner 포트 구현 — 2단계(준비/오프라인 실행) 샌드박스 호출 | M1 |
| `sandbox/docker_sandbox.py` | 범용 Docker 실행 래퍼 — 기본 네트워크 차단, 마운트 통제 | M1 |
| `examples/demo/` | PoC 대상 예제 Maven 프로젝트 (Calculator — divide는 미검증 표적) | M1 |
| `llm/__init__.py` | llm 층 선언 — 모든 LLM 호출의 유일한 통로(R7) | M0 |
| `llm/client.py` | 공용 타입(ChatMessage·ChatResponse)과 LlmClient 포트 | M2 |
| `llm/gateway.py` | 사내 게이트웨이 실호출 클라이언트 (Azure OpenAI 호환, 환경변수로만 설정) | M2 |
| `llm/replay.py` | record & replay 카세트 장치 — 재생 실패 시 폴백 없음 | M2 |
| `llm/config.py` | .env 로딩·deployment 선택 — 클라이언트 생성의 유일한 입구 | ADR-0011 |
| `llm/prompts/` | 프롬프트 파일 보관소 (system.md, write_test.md) | M0 |
| `llm/generation.py` | 프롬프트 렌더링 + chat → 테스트 코드 (TestCodeGenerator 구현) | M3 |
| `core/tools/` | 도구 6개 — 1도구 1파일, 문자열 반환 + clip 상한(R4) | M3 |
| `core/writer_graph.py` | 테스트 작성 서브그래프(LangGraph) — 반복·상한·interrupt 골격 | M3 |
| `adapters/java/inspector.py` | 대상 조사 실물 (클래스 파일 탐색 + 메서드 확인) | M3 |
| `adapters/java/similar.py` | 파싱 기반 유사 테스트 검색 (2단계에서 Neo4j로 교체) | M3 |
| `adapters/java/writer.py` | 테스트 쓰기 + 오프라인 컴파일 검사, 테스트 폴더 범위 강제 | M3 |
| `adapters/java/quality.py` | assert 수 비교 검사 최소본 (AST 비교는 2단계) | M3 |
| `adapters/java/parsing.py` | 시그니처·본문 최소 파싱 공용 헬퍼 | M3 |
| `evals/golden_case.py` | 대표 검증 시나리오 배선 단일 정의 (기록 생성·재생 공유) | M3 |
| `graph/model.py` | 그래프 노드·엣지 모델 (확정 엣지 3종) | M4 |
| `graph/store.py` | GraphStore 인터페이스 + 인메모리 구현 | M4 |
| `graph/neo4j_store.py` | Neo4j 실물 저장소 (샌드박스 밖 별도 컨테이너, v4 6.5) | M4 |
| `graph/answers.py` | 그래프 질의 → 답 문장 (CodeGraph 구현) | M4 |
| `adapters/java/graph_builder.py` | Java 소스 → 노드·엣지 (DECLARES·CREATES) | M4 |
| `adapters/java/coverage.py` | JaCoCo 실측 실행·파싱 — COVERS 근거, M6 게이트 재사용 | M4 |
| `scripts/build_graph.py` | 그래프 빌드 CLI (--coverage로 COVERS 수집) | M4 |
| `core/pipeline/models.py` | 파이프라인 데이터 모델 (변경 심볼·의도·조치) | M5 |
| `core/pipeline/decide.py` | 조치 결정 규칙표 + 지침서 조립 — LLM 금지(R2) | M5 |
| `llm/intent.py` | 의도 분류 LLM 구현 (JSON 파싱, 실패→unclear) | M5 |
| `adapters/java/changes.py` | git diff → 변경 심볼 (메서드 줄 범위 매핑) | M5 |
| `scripts/run_pipeline.py` | 파이프라인 CLI — 추출→분류→결정→사람 개입(escalate/ask 해소)→생성 | M5·M6 |
| `core/gates.py` | 게이트 실행기·설정(cta.toml) — 검문소의 언어 무관 틀 | M6 |
| `core/submit.py` | 생성→게이트 재시도 루프 (탈락 사유 반환, 소진 시 사람 확인) | M6 |
| `adapters/java/gates.py` | 게이트 ①assert ②스킵 ③범위 ④커버리지 구현 + 기준선 스냅샷 | M6 |
| `adapters/java/mutation.py` | 게이트 ⑤ PIT 뮤테이션 (overlay pom, 메서드 단위 집계) | M6 |
| `cli/main.py` | `cta` 진입점 — generate/run/diff/apply/discard/graph/eval/demo | CLI화 |
| `cli/proposals.py` | 제안 보관소 — 생성물은 apply 전까지 소스에 반영 안 됨(v4 Step 3) | CLI화 |
| `cli/generate.py` | 생성→게이트→제안 저장 조립 (구 scripts/generate_test) | CLI화 |
| `cli/file_mode.py` | `cta generate <파일명>` 간편 모드 — 파일 탐색·프로젝트 인식·메서드 선별 | 사용성 |
| `cli/locate.py` | 프로젝트 자동 인식(현재 폴더→상위→하위) — 전 명령의 --project 생략 지원 | 사용성 |
| `cli/pipeline_cmd.py` | 변경 파이프라인 조립 + escalate/ask 사람 해소 (구 run_pipeline) | CLI화 |
| `cli/graph_cmd.py`·`eval_cmd.py`·`demo_cmd.py` | graph/eval/demo 서브커맨드 | CLI화 |
| `scripts/record_golden.py` | 대표 시나리오의 LLM 호출 기록 생성 스크립트 (대본/실호출) | M3 |

## M0에서 한 구조 결정 (v4 원문 대조 완료 — 충돌 없음)

1. **src 레이아웃 대신 최상위 패키지** `core/ adapters/ llm/` — CLAUDE.md의 층 표기와
   디렉터리가 1:1로 일치해 test_layering 검사와 독자의 머릿속 지도가 단순해진다.
2. **포트는 Protocol** — Fake·실물 어댑터가 상속 없이 구조적으로 들어맞는다.
3. **빈 selector 거부는 어댑터 책임** — R5 원문("어댑터가 빈 selector를 거부한다") 그대로.
   공통 계약이므로 어댑터 테스트가 반드시 검증한다.
