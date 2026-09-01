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

`target`·`selector` 문법은 어댑터가 해석한다 — core는 불투명 문자열로 취급.

## 데이터 모델

| 모델 | 필드 | 비고 |
|---|---|---|
| `RunResult` | `passed: bool`, `summary: str` | frozen dataclass. summary는 모델에게 그대로 보여줄 요약 |
| `EmptySelectorError` | (ValueError 하위) | 전체 테스트 실행 금지(R5)의 결정적 안전장치 |

## 도구 공통 규약

- 도구 반환은 예외가 아니라 **모델이 읽을 문자열**
- 길이 상한: `core.textlimit.clip(text)` 경유, `TOOL_OUTPUT_MAX_CHARS = 4000`
  (임시값 — v4 원문 확인 필요)

## 도구 6종 (R4 — 상세 시그니처는 M3에서 확정)

v4 3절의 도구 표와 코드 식별자의 대응. 공통: 입력은 문자열, 반환은 clip을 거친 문장.

| 코드 식별자 | v4 이름 | 입력 | 출력 |
|---|---|---|---|
| `inspect_target` | 대상 조사 | 대상 메서드 식별자 | 형태·의존·기존 테스트 요약문 |
| `query_code_graph` | 코드 그래프 조회 | 사전 정의 쿼리 종류 + 대상 (자유 쿼리 금지) | 짧은 답. PoC에서는 "비슷한 모양의 테스트는?"만 파싱 기반으로 실응답 |
| `write_test` | 테스트 쓰기 | 파일 위치 + 코드 | 컴파일·정적 분석 결과 |
| `run_tests` | 테스트 실행 | 실행할 테스트 목록 + 난수 시작값(seed) | 통과/실패 + 실패 내용 |
| `check_quality` | 품질 확인 | 확인할 범위 | 커버리지·뮤테이션 지표 요약 |
| `report_finding` | 한계 보고 | 발견한 문제 | 종료 |
