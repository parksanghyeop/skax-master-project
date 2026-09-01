"""core 포트의 인메모리 Fake 구현.

왜 필요한가: M0 관문이 "Java·Docker 없이 pytest 통과"다. core·도구·서브그래프의
테스트는 전부 이 Fake로 돌려서, 실제 샌드박스 없이도 결정적으로 검증한다.
Fake는 테스트 전용이 아니라 데모·오프라인 실행에도 쓰는 정식 어댑터다.
"""

from core.ports import EmptySelectorError, RunResult


class FakeSourceInspector:
    """딕셔너리에 담긴 소스를 돌려주는 SourceInspector 구현.

    입력: sources — target 식별자 → 소스 텍스트 매핑.
    없는 target을 조회하면 예외 대신 "찾지 못했다"는 문자열을 돌려준다
    (도구 반환은 모델이 읽을 문자열이어야 하므로).
    """

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self._sources = dict(sources or {})

    def inspect(self, target: str) -> str:
        if target in self._sources:
            return self._sources[target]
        return f"대상 없음: {target!r} — 식별자를 확인하라. 알려진 대상: {sorted(self._sources)}"


class FakeTestRunner:
    """미리 정해 둔 결과를 돌려주는 TestRunner 구현.

    입력: results — selector → RunResult 매핑.
    실패 시 동작: 빈/공백 selector는 EmptySelectorError로 거부(절대 규칙 R5).
      모르는 selector는 passed=False 결과로 돌려준다 — 실제 어댑터에서도
      "해당 테스트 없음"은 예외가 아니라 실행 결과이기 때문이다.
    """

    def __init__(self, results: dict[str, RunResult] | None = None) -> None:
        self._results = dict(results or {})
        self.calls: list[str] = []  # 테스트에서 호출 순서를 검증하기 위한 기록

    def run(self, selector: str) -> RunResult:
        # 결정적 안전장치(R2·R5): 빈 selector = 전체 실행이므로 무조건 거부.
        if not selector.strip():
            raise EmptySelectorError("빈 selector — 전체 테스트 실행은 금지다(R5)")
        self.calls.append(selector)
        if selector in self._results:
            return self._results[selector]
        return RunResult(passed=False, summary=f"해당 selector의 테스트 없음: {selector!r}")
