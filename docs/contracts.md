# contracts.md — 데이터 모델·도구 시그니처

모든 작업 전에 이 문서를 확인한다. 코드와 어긋나면 코드를 고치기 전에 사용자에게 알린다.

> ⚠️ 원본 v4 설계 문서(`02_상세설계_및_개발환경구축_v4.md`)가 아직 리포에 없다.
> 이 문서는 M0 시점에 CLAUDE.md·phase1 스킬로부터 역산해 작성한 것으로,
> v4 원문이 들어오면 대조해서 어긋난 곳을 고쳐야 한다 (poc-findings '설계 수정 필요' 참조).

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

## 도구 6종 (R4 — M3에서 시그니처 확정 예정)

`inspect_target` · `query_code_graph` · `write_test` · `run_tests` · `check_quality` · `report_finding`

M0 시점에는 이름만 고정. 인자·반환 시그니처는 M3 구현 시 이 표를 채운다.
