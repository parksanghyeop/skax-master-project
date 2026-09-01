# poc-findings.md — 1단계 PoC 발견 사항 축적

제출 양식(핵심 구현 / 문제 해결·리서치 / 핵심 동작 검증)의 원재료 파일.
완성 시점마다 그 자리에서 기록한다 — 리서치 출처는 나중에 복원이 안 된다.

## 구현 내역 (→ 양식 1. 핵심 구현 내용)

### 워크플로우
- **[M3] LangGraph 테스트 작성 서브그래프** (2026-09-01)
  - 구현 기능: 정보 수집 → 생성·쓰기 → 실행 → 분기(품질/재시도/질문/한계 보고)의
    반복 그래프(v4 2.3), interrupt 지점 골격(PoC는 자동 "계속" 스텁 UserGate)
  - 동작 원리: 상태(WriterState)에 시도 횟수를 숫자로 기록하고 소프트 한도(3회)마다
    질문, 하드 캡(6회)에서 한계 보고로 정상 종료 — 조용한 무한 반복 없음.
    노드 함수는 그래프 없이 단독 테스트 가능(Fake 포트 5종으로 5개 흐름 검증)
  - 주요 기술: LangGraph StateGraph·conditional edges, 포트 주입(클로저), TypedDict 상태

### 도구·함수 연동
- **[M0] 포트·Fake 어댑터 골격** (2026-09-01)
  - 구현 기능: core 포트 2종(SourceInspector, TestRunner)과 인메모리 Fake, 도구 반환 길이 상한(clip)
  - 동작 원리: core는 Protocol 인터페이스만 정의하고 구체 구현은 adapters/에 격리.
    빈 selector는 어댑터가 EmptySelectorError로 결정적 거부(R5)
  - 주요 기술: Python Protocol(구조적 타이핑), frozen dataclass, pytest
- **[M1] Java 어댑터 + 2단계 Docker 샌드박스** (2026-09-01)
  - 구현 기능: Maven 프로젝트 탐지, 준비(go-offline+예열)/실행(오프라인) 2단계 실행,
    범용 Docker 래퍼(sandbox/)
  - 동작 원리: 준비 단계만 네트워크를 켜 의존성 캐시를 채우고, 실행 단계는
    `--network none` + `mvn -o` + 캐시 읽기 전용 마운트로 격리(v4 6.3).
    안전 불변식(빈 selector 거부, 차단 플래그)은 스텁 샌드박스 단위 테스트로 고정
  - 주요 기술: Docker(`--network none`, ro 마운트), Maven go-offline, surefire 출력 파싱
- **[M3] 도구 6개 골격** (2026-09-01)
  - 구현 기능: inspect_target·query_code_graph·write_test·run_tests·check_quality·
    report_finding — 1도구 1파일(core/tools/), 전부 문자열 반환 + clip 상한
  - 동작 원리: 도구는 포트만 알고 언어를 모른다(R1). 오류도 예외 대신 "다음 행동을
    안내하는 문장"(예: 모르는 쿼리 → 허용 목록 제시). query_code_graph는 PoC에서
    similar_tests만 실응답, 나머지 5종 쿼리는 "그래프 없음(2단계)" 안내
  - 주요 기술: 포트/어댑터 분리, 결정적 범위 검사(테스트 폴더 밖 쓰기 거부)

### 데이터·컨텍스트
- **[M2] llm/ 계층 — record & replay** (2026-09-01)
  - 구현 기능: LlmClient 포트 + 게이트웨이 실호출/녹음/재생 3구현, JSON 카세트
  - 동작 원리: 녹음은 실호출을 감싸 요청·응답을 파일에 누적, 재생은 순서대로
    요청을 대조하며 응답만 돌려준다. 카세트 없음·소진·불일치는 CassetteError로
    즉시 실패 — 실호출 폴백 없음(R7). 시크릿은 카세트에 애초에 담지 않는다
  - 주요 기술: 표준 라이브러리 urllib(의존성 0), OpenAI 호환 형식 가정, monkeypatch 테스트
- **[M3] 파싱 기반 few-shot 검색 (컨텍스트 최소본)** (2026-09-01)
  - 구현 기능: "비슷한 모양의 테스트는?" 쿼리의 그래프 없는 구현 — 기존 @Test
    메서드를 파싱해 모양 거리(파라미터 수 차이 + 예외 유무 불일치)로 상위 2개 발췌
  - 동작 원리: 좋은 본보기 = 내용이 아니라 모양이 비슷(v4 5절). 발췌는 프롬프트의
    [비슷한 모양의 기존 테스트] 절로 들어간다. 2단계에서 Neo4j 쿼리로 교체될 자리
  - 주요 기술: 정규식 시그니처 추출 + 중괄호 대응 본문 추출 (전용 파서는 2단계 검토)

## 문제·리서치 로그 (→ 양식 2. 문제 해결 및 기술 리서치)

- **[이슈 구분: 환경/문서] v4 설계 원문이 리포에 없음 → 해결** (2026-09-01)
  - 문제와 원인: CLAUDE.md가 진실의 원천으로 지정한 v4 원문이 M0 착수 시점에 리포에 없었다
  - 적용한 해결: M0는 CLAUDE.md·스킬로 역산 진행 → 사용자가 `docs/`에 원문 반입 →
    contracts.md·architecture.md를 v4 기준으로 대조·동기화. 충돌 없음 확인
  - 남은 일: v4 부록이 참조하는 상세 문서(ADR 9건, `docs/design/diagrams.md`,
    `references/build-order.md`)는 여전히 미반입. 새 ADR 번호는 10번부터 쓰면 안전하나
    기존 결정 원문이 없으므로, 기존 ADR과 충돌 의심 시 사용자에게 확인한다

## 검증 캡처 (→ 양식 3. 핵심 동작 검증)

**골든 케이스: Calculator#divide에 새 테스트 생성** (2026-09-01, 재현 가능)

- 입력 명령: `pytest -m docker tests/test_golden_case_docker.py`
  (카세트: `evals/golden/generate_divide_test.json` — 지우지 말 것)
- 도구 호출 순서 (서브그래프 트레이스):
  1. `inspect_target(Calculator#divide)` → Calculator.java 전체 + 대상 메서드 확인
  2. `query_code_graph(similar_tests, Calculator#divide)` → CalculatorTest.add 본보기 2건 발췌
  3. LLM 생성(카세트 재생, 비용 0) → CalculatorDivideTest.java (정상 나눗셈 + 0 나누기 예외)
  4. `write_test` → 테스트 폴더 안 확인 후 쓰기, 오프라인 `test-compile` 성공
  5. `run_tests(CalculatorDivideTest)` → 네트워크 차단 실행, `통과 / Tests run: 2, Failures: 0`
  6. `check_quality` → `통과: 새 테스트, assert 2개`
- 최종 결과: status=passed, 시도 1회, 소요 35.4초 (1 passed)
- ⚠️ 카세트는 게이트웨이 미접속 환경이라 대본(ScriptedLlm) 녹음본이다.
  사내망에서 `scripts/record_golden.py`의 클라이언트를 GatewayClient로 바꿔 재녹음한다

## 문제·리서치 로그 (추가분)

- **[이슈 구분: 도구 연동] 정규식이 @Test의 "Test"를 반환 타입으로 삼킴** (2026-09-01)
  - 문제와 원인: 메서드 시그니처 정규식의 느슨한 선두([\w\s]+?)가 `@Test`의 `Test`부터
    매칭을 시작해, 어노테이션 인식 창에 `@Test`가 남지 않아 is_test가 전부 False
  - 리서치 출처: 자체 디버깅 (pytest 실패 2건 역추적)
  - 적용한 해결: 선두에 `(?<![@\w])` lookbehind — 단어·@ 중간에서 매칭 시작 금지
  - 전후 변화: 유사 테스트 검색 0건 → 본보기 2건 정상 발췌. 정규식 파싱의 한계
    사례로 기록 — 2단계에서 전용 파서(tree-sitter 등) 도입 검토 근거

## 설계 수정 필요 — v4 문서·ADR과 다르게 가야 하는 지점 + 이유 (→ ADR 후보)

- **ADR-0010 작성 완료**: 개발 LLM 백엔드를 Claude API로, 운영을 사내 게이트웨이로
  이원화. `llm/config.py` 팩토리로 전환, 시크릿은 환경변수/.env로만 (2026-09-01, 사용자 결정)

- `TOOL_OUTPUT_MAX_CHARS = 4000`은 임시값 — v4 원문에 상한이 정의돼 있는지 확인 필요

## 2단계 반영 목록 — 우선순위 순

- (아직 없음)

## 측정 메모 — 토큰/시간/재시도 횟수 대략값

- M1 통합(최초 실행): 이미지 풀(802MB) + go-offline + 예열 + 오프라인 실행 = 총 3분 25초.
  캐시 완성 후 오프라인 실행 단독은 수십 초 수준으로 예상 — 2단계 분리의 효과
- M3 골든 케이스(캐시 준비된 상태): 서브그래프 전체(컴파일 검사 + 오프라인 실행 포함)
  35.4초. LLM 토큰 0 (카세트 재생) — 실호출 측정은 게이트웨이 접속 후

## 1주차 확인 의무 3건 — 개발 환경(Claude 백엔드, ADR-0010) 기준 확인 완료 (2026-09-01)

| # | 확인할 것 | 개발 환경 결과 | 사내 환경 |
|---|---|---|---|
| 1 | 임베딩 API 제공 여부 | ❌ **미제공** — Anthropic API에는 임베딩 엔드포인트가 없다(공식 문서·claude-api 스킬 확인, 외부 임베딩 서비스 권장 구조). → v4 4.1 ④ 보조 검색(커밋 메시지·판단 메모)은 **보류**, 코드 그래프 주 검색만으로 2단계 진행 | ⏳ 게이트웨이 확인 후 재평가 |
| 2 | Neo4j 별도 구동 가능 여부 | ✅ **가능** — `neo4j:5` 컨테이너 단독 기동 후 `cypher-shell RETURN 1` 응답 확인(실측). v4 6.5의 "샌드박스 밖 별도 컨테이너" 구조 성립 | ⏳ 사내망 정책 확인 필요 |
| 3 | tool calling 지원 여부 | ✅ **지원** — Claude Messages API는 tools/tool_use를 정식 지원(공식 문서 확인). 단 PoC 파이프라인은 이미 텍스트(코드 블록) 파싱 방식이라 모델 무관 동작 — tool calling 전환은 2단계에서 도구 6종을 모델에 직접 노출할 때 결정 | ⏳ Kimi/Qwen/GLM 모델별 확인, 미지원 시 현행 파싱 방식 유지 |

- 리서치 출처: claude-api 스킬(2026-06 캐시) + platform.claude.com 공식 문서 체계.
  실호출 스모크 테스트는 `.env`에 `ANTHROPIC_API_KEY` 설정 후
  `scripts/record_golden.py --live`로 수행 예정(키는 사용자 보유)
