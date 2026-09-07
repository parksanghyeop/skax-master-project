"""변경 대응 파이프라인의 분석 단계 — 변경 건별 의도 분류 → 기존 테스트 상태 → 조치 결정.

시나리오 SC-002/003의 1~5단계를 포트만으로 조립한 순수 함수다. CLI는 이 결과를
화면에 그리고(cli/render), create_test는 생성 명령으로, escalate/ask는 저장 후
멈춤(cli/escalations)으로 넘긴다. 층: core — 언어·git·LLM 구현을 모른다(R1·R7).
"""

from collections.abc import Callable
from dataclasses import dataclass

from cta.core.pipeline.decide import decide
from cta.core.pipeline.models import (
    INTENT_TRIVIAL,
    INTENT_UNCLEAR,
    KNOWN_INTENTS,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    ActionDecision,
    ChangedSymbol,
    ChangeSet,
    Intent,
)
from cta.core.ports import IntentClassifier, TestLocator, TestRunner

# 주석·공백만 바뀐 변경의 고정 판정 — LLM을 부르지 않는다(ADR-0015 D2). 확신도 1.0은
# "결정적으로 판정했다"는 뜻이지 모델의 추정치가 아니다.
TRIVIAL_INTENT = Intent(
    category=INTENT_TRIVIAL,
    analysis="주석·공백만 바뀌어 시험할 동작이 없다.",
    confidence=1.0,
    evidence=("주석만 수정됨 (코드 줄 변경 0)",),
)


# 작성자가 --intent로 지정할 수 있는 값.
# trivial(코드가 판정)·unclear(모른다는 뜻)는 지정 대상이 아니다.
AUTHOR_INTENTS = tuple(c for c in KNOWN_INTENTS if c not in (INTENT_TRIVIAL, INTENT_UNCLEAR))


def with_author_intent(intent: Intent, category: str) -> Intent:
    """작성자가 밝힌 의도로 분류(category)를 덮어쓴다 (ADR-0020 D1).

    왜 필요한가: 미커밋 변경은 커밋 메시지가 없어 모델이 unclear로 갈 수 있다. 사람이 말한
    의도는 R3의 "추측"이 아니므로 그대로 쓴다. LLM의 근거·분석은 유지한다(지침서 재료).
    입력: intent 모델 분류 결과, category AUTHOR_INTENTS 중 하나.
    출력: category가 바뀌고 확신도 1.0, 근거 첫 줄에 "작성자 지정 의도"가 붙은 Intent.
    실패 시 동작: 허용되지 않는 값이면 ValueError — CLI가 choices로 먼저 막는다.
    """
    if category not in AUTHOR_INTENTS:
        raise ValueError(f"작성자 지정 의도로 쓸 수 없는 값: {category!r} (허용: {AUTHOR_INTENTS})")
    return Intent(
        category=category,
        analysis=intent.analysis,
        confidence=1.0,
        evidence=(f"작성자 지정 의도: {category} (--intent)",) + tuple(intent.evidence),
    )


@dataclass(frozen=True)
class ChangeAnalysis:
    """변경 한 건의 분석 결과 — 화면 출력(①②…)과 후속 처리의 단위."""

    change: ChangedSymbol
    intent: Intent
    tests: list[str]  # 대상을 검증하는 기존 테스트 selector들(없으면 빈 목록)
    tests_status: str  # TESTS_PASS / TESTS_FAIL / TESTS_NONE
    run_summary: str  # 기존 테스트 실행 요약(실패 상세 포함). 실행 안 했으면 빈 값
    decision: ActionDecision
    memos: str  # 비슷한 과거 판단 사례(참고용 문자열). 없으면 빈 값


def analyze_changes(
    change_set: ChangeSet,
    classifier: IntentClassifier,
    locator: TestLocator,
    runner: TestRunner,
    memo_lookup: Callable[[str], str] | None = None,
    progress: Callable[[str], None] | None = None,
    author_intent: str | None = None,
) -> list[ChangeAnalysis]:
    """변경 건마다 (의도, 기존 테스트 상태, 조치)를 정한다.

    입력: change_set 변경 추출 결과, classifier 의도 분류(LLM), locator 검증 테스트 찾기,
      runner 테스트 실행(샌드박스), memo_lookup 대상 → 과거 사례 문자열(없으면 빈 값),
      author_intent 작성자가 지정한 의도(--intent, 없으면 None) — 주석만 변경은 그래도 trivial.
    출력: 심볼 순서대로의 ChangeAnalysis 목록.
    같은 테스트 묶음은 한 번만 실행한다(여러 변경이 같은 테스트 클래스에 걸리는 흔한 경우).
    """
    report = progress or (lambda _msg: None)
    lookup = memo_lookup or (lambda _target: "")
    run_cache: dict[str, tuple[str, str]] = {}
    analyses: list[ChangeAnalysis] = []
    for change in change_set.symbols:
        memos = lookup(change.target)
        if change.comment_only:
            intent = TRIVIAL_INTENT
        else:
            report(f"의도 분류 중 — {change.target}")
            intent = classifier.classify(change, change_set, memos)
            if author_intent:
                intent = with_author_intent(intent, author_intent)
        tests = locator.find(change.target)
        if not tests or intent.category == INTENT_TRIVIAL:
            # 의미 없는 변경은 테스트를 돌려 볼 이유가 없다 — 규칙표가 상태와 무관하게 no_action
            status, summary = TESTS_NONE, ""
        else:
            selector = ",".join(tests)
            if selector not in run_cache:
                report(f"기존 테스트 실행 중 — {selector}")
                result = runner.run(selector)
                run_cache[selector] = (
                    TESTS_PASS if result.passed else TESTS_FAIL,
                    result.summary,
                )
            status, summary = run_cache[selector]
        decision = decide(change, intent, status)
        analyses.append(
            ChangeAnalysis(
                change=change,
                intent=intent,
                tests=list(tests),
                tests_status=status,
                run_summary=summary,
                decision=decision,
                memos=memos,
            )
        )
    return analyses
