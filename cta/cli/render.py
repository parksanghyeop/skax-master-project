"""화면 출력 형식 — 시나리오수립.md의 "기대 출력"을 그대로 따르는 문자열 조립.

CLI의 모든 서브커맨드가 같은 모양(①② 항목, 판단/근거/할 일, 상자, 결과 상태)을 쓰도록
여기 모은다. 판단 로직은 없다 — 받은 값을 글자로 바꿀 뿐이다. 층: cli.
"""

from cta.core.pipeline.maintain import ChangeAnalysis
from cta.core.pipeline.models import (
    ACTION_ASK,
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    ACTION_NO_ACTION,
    INTENT_BUG_FIX,
    INTENT_NEW_FEATURE,
    INTENT_REFACTOR,
    INTENT_TRIVIAL,
    INTENT_UNCLEAR,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
)

# 결과 상태 — 시나리오의 마지막 줄. 종료 코드와 1:1이다(CI에서 그대로 쓴다).
STATUS_OK = "정상 완료"  # 0
STATUS_HUMAN = "사람 확인 필요"  # 3
STATUS_QUALITY = "품질 미달"  # 2
STATUS_ERROR = "실패"  # 1
EXIT_CODES = {STATUS_OK: 0, STATUS_HUMAN: 3, STATUS_QUALITY: 2, STATUS_ERROR: 1}

INTENT_LABELS = {
    INTENT_BUG_FIX: "버그 수정",
    INTENT_REFACTOR: "리팩터링 (동작 안 바뀜)",
    INTENT_NEW_FEATURE: "새 기능",
    INTENT_TRIVIAL: "의미 없는 변경",
    INTENT_UNCLEAR: "판단 불확실",
}

_STATUS_LABELS = {TESTS_PASS: "통과", TESTS_FAIL: "실패", TESTS_NONE: "없음"}

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

INDENT = "  "


def circled(index: int) -> str:
    """1부터 시작하는 번호를 ①②…로. 20을 넘으면 (21) 형식."""
    return _CIRCLED[index - 1] if 1 <= index <= len(_CIRCLED) else f"({index})"


def display_target(target: str) -> str:
    """ "OrderService#applyDiscount" → "OrderService.applyDiscount" (시나리오 표기)."""
    return target.replace("#", ".")


def action_label(analysis: ChangeAnalysis) -> str:
    kind = analysis.decision.kind
    if kind == ACTION_CREATE_TEST:
        return (
            "재발 방지 테스트 추가" if analysis.intent.category == INTENT_BUG_FIX else "테스트 추가"
        )
    if kind == ACTION_NO_ACTION:
        return "없음"
    if kind == ACTION_ESCALATE:
        return "사람 확인 (자동으로 고치지 않음)"
    if kind == ACTION_ASK:
        return "사람에게 질문"
    return kind


def box(title: str) -> str:
    """시나리오의 상자 — 제목 한 줄을 ┌─┐│└─┘로 감싼다."""
    width = max(54, _width(title) + 6)
    pad = width - 2 - _width(title) - 2
    return (
        f"{INDENT}┌{'─' * (width - 2)}┐\n"
        f"{INDENT}│  {title}{' ' * pad}│\n"
        f"{INDENT}└{'─' * (width - 2)}┘"
    )


def _width(text: str) -> int:
    # 한글·전각 기호는 터미널에서 2칸 — 상자 테두리를 맞추기 위한 근사
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def render_analysis(index: int, analysis: ChangeAnalysis) -> str:
    """변경 한 건의 판단 블록 — 사용자가 의도 분석 결과를 반드시 볼 수 있게 전부 적는다."""
    label = INTENT_LABELS.get(analysis.intent.category, analysis.intent.category)
    confidence = f"(확신도 {analysis.intent.confidence:.0%})"
    lines = [f"{INDENT}{circled(index)} {display_target(analysis.change.target)}"]
    lines.append(f"{INDENT}   판단   {label:<18}{confidence}")
    evidence = list(analysis.intent.evidence) or ["(근거 없음)"]
    lines.append(f"{INDENT}   근거   · {evidence[0]}")
    for item in evidence[1:]:
        lines.append(f"{INDENT}          · {item}")
    if analysis.intent.category not in (INTENT_TRIVIAL,):
        lines.append(f"{INDENT}   분석   {analysis.intent.analysis}")
    tests = ", ".join(analysis.tests) if analysis.tests else "없음"
    status = _STATUS_LABELS.get(analysis.tests_status, analysis.tests_status)
    if analysis.intent.category != INTENT_TRIVIAL:
        lines.append(f"{INDENT}   기존 테스트   {tests}  → {status}")
    lines.append(f"{INDENT}   참고   {analysis.memos or '비슷한 과거 사례 없음'}")
    lines.append(f"{INDENT}   할 일  {action_label(analysis)}")
    return "\n".join(lines)


def render_result_status(status: str) -> str:
    return f"\n{INDENT}결과 상태: {status}"


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}분 {secs}초" if minutes else f"{secs}초"


def format_tokens(tokens: int) -> str:
    return f"{tokens:,} 토큰" if tokens else "토큰 수 미제공"


def render_diff_excerpt(diff_excerpt: str, max_lines: int = 6) -> list[str]:
    """ "바뀌기 전/바뀐 후" — diff 발췌에서 -/+ 줄을 각각 몇 줄씩 보여준다."""
    before = [ln[1:].strip() for ln in diff_excerpt.splitlines() if ln.startswith("-")]
    after = [ln[1:].strip() for ln in diff_excerpt.splitlines() if ln.startswith("+")]
    lines = []
    for label, items in (("바뀌기 전", before), ("바뀐 후  ", after)):
        if not items:
            lines.append(f"{label} : (없음)")
            continue
        lines.append(f"{label} : {items[0]}")
        for extra in items[1:max_lines]:
            lines.append(f"            {extra}")
        if len(items) > max_lines:
            lines.append(f"            … 외 {len(items) - max_lines}줄")
    return lines
