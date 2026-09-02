"""Maven·surefire 출력 해석 — 실패 테스트(이름·기대·실제), 컴파일 오류 수, 실행 테스트 수.

시나리오의 화면 출력("1차 컴파일 실패 2건 — …", "기대 0, 실제 null", "테스트 9개")은
전부 이 파일의 결정적 파싱에서 나온다. LLM은 관여하지 않는다(R2). 층: adapters/java.
"""

import re
from dataclasses import dataclass

# surefire 실패 요약 줄 예: "[ERROR]   CalcTest.calculate_empty:19 expected: <0> but was: <null>"
_FAILURE_SUMMARY = re.compile(
    r"\[ERROR\]\s+(?P<cls>\w+)\.(?P<name>\w+)(?::\d+)?\s+(?P<message>.+)$"
)
# 실행 중 실패 표식 예: "[ERROR] CalcTest.calculate_empty -- Time elapsed: 0.1 s <<< FAILURE!"
_FAILURE_MARK = re.compile(
    r"\[ERROR\]\s+(?P<cls>\w+)\.(?P<name>\w+)\s+--\s+Time elapsed.*<<<\s*(?:FAILURE|ERROR)"
)
_EXPECTED_ACTUAL = re.compile(r"expected:\s*<(?P<expected>.*?)>\s*but was:\s*<(?P<actual>.*?)>")
_TESTS_RUN = re.compile(r"Tests run:\s*(\d+)")
_RUN_STATS = re.compile(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)")
_COMPILE_ERROR = re.compile(r"\.java:\[(\d+),(\d+)\]\s*(?P<message>.*)$")


@dataclass(frozen=True)
class FailedTest:
    """실패한 테스트 하나 — 사람 확인 보고서(SC-003)의 "실패한 테스트" 항목."""

    name: str  # 테스트 메서드 이름
    test_class: str
    expected: str  # 파싱 못 하면 빈 문자열
    actual: str
    message: str  # 원문 한 줄


def parse_failed_tests(output: str) -> list[FailedTest]:
    """실행 출력에서 실패 테스트 목록을 뽑는다. 같은 테스트는 한 번만."""
    found: dict[str, FailedTest] = {}
    for line in output.splitlines():
        m = _FAILURE_SUMMARY.match(line.strip())
        if not m or "Time elapsed" in line:
            continue
        message = m.group("message").strip()
        ea = _EXPECTED_ACTUAL.search(message)
        key = f"{m.group('cls')}.{m.group('name')}"
        found[key] = FailedTest(
            name=m.group("name"),
            test_class=m.group("cls"),
            expected=ea.group("expected") if ea else "",
            actual=ea.group("actual") if ea else "",
            message=message,
        )
    if found:
        return list(found.values())
    # 요약 절이 잘렸을 때의 폴백 — 실행 중 실패 표식만이라도 이름을 건진다
    for line in output.splitlines():
        m = _FAILURE_MARK.search(line)
        if m:
            key = f"{m.group('cls')}.{m.group('name')}"
            found.setdefault(key, FailedTest(m.group("name"), m.group("cls"), "", "", line.strip()))
    return list(found.values())


def count_tests_run(output: str) -> int:
    """실행된 테스트 수. surefire는 클래스별·합계 줄을 모두 찍으므로 가장 큰 값이 합계다."""
    counts = [int(n) for n in _TESTS_RUN.findall(output)]
    return max(counts) if counts else 0


def compile_errors(write_result: str) -> list[str]:
    """컴파일 검사 결과에서 오류 메시지들을 뽑는다 (같은 메시지는 한 번만)."""
    messages: list[str] = []
    for line in write_result.splitlines():
        m = _COMPILE_ERROR.search(line)
        if m:
            message = m.group("message").strip()
            if message and message not in messages:
                messages.append(message)
    return messages


def describe_attempt(write_result: str, run_result: str) -> str:
    """회차 한 줄 요약 — "컴파일 실패 2건 — …" / "실행 실패 1건 — 기대 …, 실제 …" / "전체 통과"."""
    if "컴파일 실패" in write_result:
        errors = compile_errors(write_result)
        detail = "; ".join(e[:60] for e in errors[:2])
        return f"컴파일 실패 {len(errors) or 1}건" + (f" — {detail}" if detail else "")
    if run_result.startswith("통과"):
        return "전체 통과"
    failed = parse_failed_tests(run_result)
    if failed:
        first = failed[0]
        detail = (
            f"기대 {first.expected}, 실제 {first.actual}"
            if first.expected or first.actual
            else first.message[:60]
        )
        return f"실행 실패 {len(failed)}건 — {detail}"
    if "실행 거부" in run_result or "시간 초과" in run_result:
        return run_result.splitlines()[0][:80]
    # 실패 요약 줄을 못 찾은 경우(예: Mockito 설정 오류 = Errors) — 합계 줄로라도 규모를 알린다
    stats = _RUN_STATS.findall(run_result)
    if stats:
        run, failures, errors = (int(x) for x in stats[-1])
        return f"실행 실패 — {run}개 중 실패 {failures}건, 오류 {errors}건"
    return "실행 실패 — " + (run_result.splitlines()[1][:60] if "\n" in run_result else "원인 미상")
