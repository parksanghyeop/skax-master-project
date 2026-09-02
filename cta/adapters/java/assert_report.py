"""assert 비교 보고 — 테스트 메서드 단위로 "바뀌기 전/후"와 엄격함 점수를 만든다 (SC-004).

게이트 ①(AssertIntegrityGate)이 탈락 사유를 사람이 읽을 형태로 만들 때 쓴다:
  applyDiscount_goldMember_appliesRate
    바뀌기 전 : 결과가 정확히 8500인지 확인   (4점)
    바뀐 후   : 결과가 null이 아닌지만 확인   (1점)
점수표는 고정값이다 — 판단이 아니라 "어떤 assert가 더 많은 것을 확인하는가"의 관례적
순위(같음 4 > 참/거짓 3 > null임 2 > null 아님 1). LLM 없음(R2). 층: adapters/java.
"""

import re
from dataclasses import dataclass

from cta.adapters.java.parsing import extract_assert_statements, extract_methods

# assert 이름 → 엄격함 점수. 없는 이름은 기본 2점.
_STRICTNESS = {
    "assertEquals": 4, "assertSame": 4, "assertArrayEquals": 4, "assertIterableEquals": 4,
    "assertLinesMatch": 4, "isEqualTo": 4, "isEqualByComparingTo": 4, "containsExactly": 4,
    "assertThrows": 4, "assertThrowsExactly": 4, "assertThatThrownBy": 4, "isInstanceOf": 4,
    "assertTrue": 3, "assertFalse": 3, "isTrue": 3, "isFalse": 3, "hasSize": 3, "contains": 3,
    "assertNull": 2, "isNull": 2, "isEmpty": 2, "assertNotEquals": 2,
    "assertNotNull": 1, "isNotNull": 1, "isNotEmpty": 1, "assertDoesNotThrow": 1,
}  # fmt: skip
_DEFAULT_SCORE = 2

_NAME = re.compile(r"^(\w+)\s*\(")
_THROWN_TYPE = re.compile(r"(\w+)\.class")


@dataclass(frozen=True)
class AssertChange:
    """테스트 메서드 하나에서 발견한 assert 변화."""

    test_name: str
    before: str  # 원문 assert (정규화) — 삭제된 테스트면 빈 값
    after: str  # 대체된 assert — 없으면 빈 값(삭제)
    removed_test: bool = False


def strictness(statement: str) -> int:
    m = _NAME.match(statement)
    return _STRICTNESS.get(m.group(1), _DEFAULT_SCORE) if m else _DEFAULT_SCORE


def _first_argument(statement: str) -> str:
    """첫 인자 텍스트 — 괄호 깊이를 세어 `new BigDecimal("8500")` 같은 중첩 호출도 통째로 잡는다."""
    start = statement.find("(")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(statement)):
        ch = statement[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return statement[start + 1 : i].strip()
        elif ch == "," and depth == 1:
            return statement[start + 1 : i].strip()
    return ""


def describe(statement: str) -> str:
    """assert 문을 한 줄 한국어로 — 뜻을 이해하는 게 아니라 이름·첫 인자를 틀에 넣는다."""
    m = _NAME.match(statement)
    name = m.group(1) if m else ""
    arg = _first_argument(statement)
    if name in ("assertEquals", "assertSame", "assertArrayEquals", "assertIterableEquals"):
        return f"결과가 정확히 {arg}인지 확인" if arg else "결과가 정확한 값인지 확인"
    if name in ("assertThrows", "assertThrowsExactly", "assertThatThrownBy"):
        thrown = _THROWN_TYPE.search(statement)
        return f"{thrown.group(1)} 예외가 나는지 확인" if thrown else "예외가 나는지 확인"
    if name == "assertTrue":
        return "조건이 참인지 확인"
    if name == "assertFalse":
        return "조건이 거짓인지 확인"
    if name == "assertNull":
        return "결과가 null인지 확인"
    if name == "assertNotNull":
        return "결과가 null이 아닌지만 확인"
    if name == "assertDoesNotThrow":
        return "예외가 안 나는지만 확인"
    return statement[:70]


def _asserts_by_test(source: str) -> dict[str, list[str]]:
    return {m.name: extract_assert_statements(m.text) for m in extract_methods(source) if m.is_test}


def compare_test_asserts(before_source: str, after_source: str) -> list[AssertChange]:
    """수정 전·후 테스트 소스를 테스트 메서드 단위로 비교해 훼손된 assert를 찾는다.

    규칙: 기존 assert 문이 사라지면 훼손. 같은 메서드에 새로 생긴 assert가 있으면 그것을
    "바뀐 후"로 짝지어 보여준다(완화 의심). 테스트 메서드 자체가 없어지면 삭제로 보고.
    새 assert 추가·새 테스트 추가는 자유다.
    """
    before = _asserts_by_test(before_source)
    after = _asserts_by_test(after_source)
    changes: list[AssertChange] = []
    for name, old_stmts in before.items():
        if name not in after:
            changes.append(AssertChange(name, "; ".join(old_stmts), "", removed_test=True))
            continue
        new_stmts = list(after[name])
        replacements = [s for s in new_stmts if s not in old_stmts]
        for stmt in old_stmts:
            if stmt in new_stmts:
                new_stmts.remove(stmt)
                continue
            replacement = replacements.pop(0) if replacements else ""
            changes.append(AssertChange(name, stmt, replacement))
    return changes


def render_changes(changes: list[AssertChange]) -> str:
    """탈락 사유 본문 — 시나리오 SC-004의 기대 출력 형식."""
    lines: list[str] = []
    for c in changes:
        lines.append(f"{c.test_name}")
        if c.removed_test:
            exception = "예외가 나는지 확인하는 " if "Throw" in c.before else ""
            lines.append(f"  {exception}테스트가 통째로 삭제됨 — {c.before[:100]}")
            continue
        lines.append(
            f"  바뀌기 전 : {describe(c.before)}   ({strictness(c.before)}점) — {c.before[:100]}"
        )
        if c.after:
            lines.append(
                f"  바뀐 후   : {describe(c.after)}   ({strictness(c.after)}점) — {c.after[:100]}"
            )
        else:
            lines.append("  바뀐 후   : 확인 문장이 삭제됨   (0점)")
    return "\n".join(lines)
