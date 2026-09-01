"""파이프라인 단계 사이를 흐르는 데이터 모델.

시그니처를 바꾸면 docs/contracts.md를 같은 커밋에서 갱신한다.
"""

from dataclasses import dataclass

# 의도 대분류 — v4 2.1 규칙표의 행 이름이자 LLM 분류 출력의 허용값.
INTENT_BUG_FIX = "bug_fix"
INTENT_REFACTOR = "refactor"
INTENT_NEW_FEATURE = "new_feature"
INTENT_UNCLEAR = "unclear"  # 분류 불확실 — 추측하지 않고 사람에게 묻는다(R3)
KNOWN_INTENTS = (INTENT_BUG_FIX, INTENT_REFACTOR, INTENT_NEW_FEATURE, INTENT_UNCLEAR)

# 기존 테스트 상태 — 조치 결정 규칙표의 열.
TESTS_PASS = "pass"
TESTS_FAIL = "fail"
TESTS_NONE = "none"  # 대상을 실측 커버하는 테스트가 없다

# 조치 종류 — 규칙표의 값. "기대값을 자동으로 고친다"는 값은 표에 아예 없다(R3).
ACTION_CREATE_TEST = "create_test"
ACTION_NO_ACTION = "no_action"
ACTION_ESCALATE = "escalate"  # 사람에게 넘긴다 (예: refactor인데 테스트 실패)
ACTION_ASK = "ask"  # 사람에게 묻는다 (분류 불확실 등)


@dataclass(frozen=True)
class ChangedSymbol:
    """변경 추출의 출력 한 건 — "어디가 바뀌었나".

    target: 대상 식별자("Class#method"). 시그니처 변경·증감 줄 수는 의도 분류의
    단서로 쓰인다(v4 2.1 Step 1).
    """

    target: str
    lines_added: int
    lines_removed: int
    signature_changed: bool
    diff_excerpt: str  # 이 심볼에 해당하는 diff 발췌 (분류 프롬프트 재료)


@dataclass(frozen=True)
class Intent:
    """의도 분류의 출력 — 대분류 하나 + 구체 분석 하나 (LLM 1회 호출, v4 2.1).

    category: KNOWN_INTENTS 중 하나. 파싱 실패·모르는 값은 unclear로 다룬다.
    analysis: 무엇이 어떻게 바뀌었고 어떤 상황을 시험해야 하는지 — 작업 지침서의 재료.
    """

    category: str
    analysis: str


@dataclass(frozen=True)
class ActionDecision:
    """조치 결정의 출력 — 갈 길(kind)과 작업 지침서(briefing).

    kind는 규칙표가 정하고(결정적), briefing은 LLM 분석을 첨부한 것일 뿐
    길을 바꾸지 못한다(v4 2.1 Step 2-B의 경계선).
    """

    kind: str
    target: str
    briefing: str
    reason: str  # 어느 규칙 행에 걸렸는지 — 보고서·디버깅용
