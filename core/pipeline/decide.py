"""조치 결정 — 규칙표 조회 + 작업 지침서 조립 (v4 2.1 Step 2).

왜 LLM을 안 쓰는가(R2, ADR 근거는 v4 2.1): 길을 잘못 고르면 사람 확인 없이
기대값이 바뀌는 사고가 난다. 그래서 길은 미리 적힌 표에서 "찾아보기"만 하고,
계산도 판단도 없다. LLM의 구체 분석은 지침서 내용으로만 쓰인다 — 지침서가
틀리면 테스트 품질이 떨어질 뿐, 사고는 아니다.
"""

from core.pipeline.models import (
    ACTION_ASK,
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    ACTION_NO_ACTION,
    INTENT_BUG_FIX,
    INTENT_NEW_FEATURE,
    INTENT_REFACTOR,
    INTENT_UNCLEAR,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    ActionDecision,
    ChangedSymbol,
    Intent,
)

# 경로 규칙표 (v4 2.1의 표를 코드로 옮긴 것). (대분류, 기존 테스트 상태) → 조치.
# "기대값을 자동으로 고친다"는 행은 여기 존재하지 않는다 — 추가 금지(R3).
_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    (INTENT_BUG_FIX, TESTS_PASS): (ACTION_CREATE_TEST, "버그 수정 → 재발 방지 테스트 신규"),
    (INTENT_BUG_FIX, TESTS_FAIL): (ACTION_CREATE_TEST, "버그 수정 → 재발 방지 테스트 신규"),
    (INTENT_BUG_FIX, TESTS_NONE): (ACTION_CREATE_TEST, "버그 수정 → 재발 방지 테스트 신규"),
    (INTENT_NEW_FEATURE, TESTS_PASS): (ACTION_CREATE_TEST, "새 기능 → 기능 테스트 신규"),
    (INTENT_NEW_FEATURE, TESTS_FAIL): (ACTION_CREATE_TEST, "새 기능 → 기능 테스트 신규"),
    (INTENT_NEW_FEATURE, TESTS_NONE): (ACTION_CREATE_TEST, "새 기능 → 기능 테스트 신규"),
    (INTENT_REFACTOR, TESTS_PASS): (
        ACTION_NO_ACTION,
        "리팩터링 + 테스트 통과 → 동작 보존 확인됨, 할 일 없음",
    ),
    # R3의 핵심 행: "동작 안 바꿨다"는데 테스트가 깨짐 = 동작이 실제로 바뀐 것.
    # 기대값을 고칠 일이 아니라 사람이 볼 일이다.
    (INTENT_REFACTOR, TESTS_FAIL): (
        ACTION_ESCALATE,
        "리팩터링인데 테스트 실패 → 동작이 바뀌었을 수 있음, 사람에게 넘김",
    ),
    # v4 표에 없는 조합 — 리팩터링인데 지켜줄 테스트가 없으면 판단이 갈릴 수 있어
    # 추측하지 않고 묻는다(보수적 기본값. 특성 테스트 자동 생성은 사용자 결정 사항)
    (INTENT_REFACTOR, TESTS_NONE): (
        ACTION_ASK,
        "리팩터링인데 커버 테스트 없음 → 특성 테스트를 만들지 사람에게 물음",
    ),
}


def decide(change: ChangedSymbol, intent: Intent, tests_status: str) -> ActionDecision:
    """규칙표에서 길을 찾고, 지침서를 조립한다.

    입력: change 변경 심볼, intent 의도 분류 결과, tests_status 기존 테스트 상태
      (TESTS_PASS/FAIL/NONE — 대상을 실측 커버하는 테스트의 실행 결과).
    출력: ActionDecision. 분류가 불확실(unclear)하면 표를 보기 전에 ASK다.
    """
    if intent.category == INTENT_UNCLEAR or intent.category not in {
        INTENT_BUG_FIX,
        INTENT_REFACTOR,
        INTENT_NEW_FEATURE,
    }:
        return ActionDecision(
            kind=ACTION_ASK,
            target=change.target,
            briefing=_briefing(change, intent),
            reason="분류 불확실 → 추측하지 않고 사람에게 묻는다(R3)",
        )
    kind, reason = _TABLE[(intent.category, tests_status)]
    return ActionDecision(
        kind=kind, target=change.target, briefing=_briefing(change, intent), reason=reason
    )


def _briefing(change: ChangedSymbol, intent: Intent) -> str:
    """작업 지침서 — LLM의 구체 분석을 결정적 틀에 끼워 넣는다 (내용만, 길은 못 바꾼다)."""
    signature_note = " (시그니처 변경됨)" if change.signature_changed else ""
    return (
        f"대상: {change.target}{signature_note}\n"
        f"변경 규모: +{change.lines_added}/-{change.lines_removed} 줄\n"
        f"분석과 시험 지침: {intent.analysis}"
    )
