"""core 포트의 인메모리 Fake 구현.

왜 필요한가: M0 관문이 "Java·Docker 없이 pytest 통과"다. core·도구·서브그래프의
테스트는 전부 이 Fake로 돌려서, 실제 샌드박스 없이도 결정적으로 검증한다.
Fake는 테스트 전용이 아니라 데모·오프라인 실행에도 쓰는 정식 어댑터다.
"""

from cta.core.ports import EmptySelectorError, RunResult, UserReply


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


class ScriptedTestRunner:
    """호출 순서대로 준비된 결과를 돌려주는 TestRunner — 재시도 루프 테스트용.

    FakeTestRunner와 달리 같은 selector라도 호출마다 다른 결과를 낼 수 있어,
    "실패 → 실패 → 통과" 같은 흐름을 대본으로 만들 수 있다.
    """

    def __init__(self, results: list[RunResult]) -> None:
        self._results = list(results)
        self.calls: list[str] = []

    def run(self, selector: str) -> RunResult:
        if not selector.strip():
            raise EmptySelectorError("빈 selector — 전체 테스트 실행은 금지다(R5)")
        self.calls.append(selector)
        if self._results:
            return self._results.pop(0)
        return RunResult(passed=False, summary="대본 소진 — 준비된 결과가 없다")


class FakeSimilarTestFinder:
    """정해진 발췌 문자열을 돌려주는 SimilarTestFinder 구현."""

    def __init__(self, examples: str = "기존 테스트 없음") -> None:
        self._examples = examples

    def find(self, target: str) -> str:
        return self._examples


class FakeCodeGraph:
    """쿼리별 준비된 답을 돌려주는 CodeGraph 구현. 없는 쿼리는 안내 문장."""

    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self._answers = dict(answers or {})
        self.calls: list[tuple[str, str]] = []

    def answer(self, query: str, target: str) -> str:
        self.calls.append((query, target))
        return self._answers.get(query, f"준비된 답 없음(Fake): {query}")


class FakeTestWriter:
    """파일을 실제로 쓰지 않고 기록만 하는 TestWriter 구현."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []

    def write(self, path: str, code: str) -> str:
        self.writes.append((path, code))
        return f"쓰기 완료(Fake): {path}"


class FakeQualityChecker:
    """정해진 결과를 돌려주는 QualityChecker 구현."""

    def __init__(self, verdict: str = "통과: 검사 생략(Fake)") -> None:
        self._verdict = verdict

    def check(self, path: str) -> str:
        return self._verdict


class ScriptedUserGate:
    """준비된 답을 차례로 돌려주는 UserGate — interrupt 지점의 PoC 스텁.

    답이 소진되면 "continue"를 계속 돌려준다(자동 계속). 실제 interrupt 연결은
    2단계 몫이고, PoC 관문에는 이 스텁이 들어간다(phase1 스킬 제외 목록).
    """

    def __init__(self, replies: list[UserReply] | None = None) -> None:
        self._replies = list(replies or [])
        self.questions: list[str] = []

    def ask(self, question: str) -> UserReply:
        self.questions.append(question)
        if self._replies:
            return self._replies.pop(0)
        return UserReply(action="continue")


class ScriptedGenerator:
    """준비된 코드를 차례로 돌려주는 TestCodeGenerator — LLM 없이 그래프를 시험한다."""

    def __init__(self, codes: list[str]) -> None:
        self._codes = list(codes)
        self.calls: list[dict] = []

    def generate(self, instruction: str, context: str, current_code: str, last_failure: str) -> str:
        self.calls.append({"instruction": instruction, "last_failure": last_failure})
        if self._codes:
            return self._codes.pop(0)
        return self._codes_exhausted()

    @staticmethod
    def _codes_exhausted() -> str:
        return "// 대본 소진\n"
