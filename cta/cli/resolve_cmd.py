"""cta resolve — 판단 전달: 저장된 사람 확인 항목을 읽어 멈춘 지점부터 이어서 실행 (SC-003 8단계).

선택지(사람이 명시적으로 고른 것만 실행한다 — R3는 '사람 확인 없는' 갱신을 막는 규칙):
  --intended    일부러 동작을 바꾼 게 맞다 → 실패한 테스트의 기대값을 새 동작 기준으로 수정
  --test-issue  테스트 쪽 문제다 → 실패한 테스트를 동작(입출력) 기준으로 다시 작성
  --proceed     (질문 항목) 계획대로 테스트 생성 (--hint로 지시 추가)
  --as <의도>   (질문 항목) 의도를 직접 지정 → 규칙표부터 다시 진행 (ADR-0020 D1, LLM 없음)
  --skip        이번엔 건너뛴다 (기록만 남김)
실패한 테스트 메서드 **만** assert 변경이 허용되고(게이트 허용 목록), 나머지는 게이트가 보호한다.
결정은 판단 메모(.cta/memos)로 남아 다음 maintain의 참고 자료가 된다. 층: cli (ADR-0015 D3).
"""

import argparse
from datetime import datetime

from cta.adapters.java.maven import detect_maven_project
from cta.cli.escalations import (
    Escalation,
    discard_escalation,
    get_escalation,
    list_escalations,
)
from cta.cli.generate import ask_on_terminal, run_generation
from cta.cli.memos import Memo, save_memo, situation_text
from cta.cli.render import (
    EXIT_CODES,
    INDENT,
    INTENT_LABELS,
    STATUS_OK,
    display_target,
    render_result_status,
)
from cta.core.agent import ENGINE_LEGACY
from cta.core.pipeline.decide import decide
from cta.core.pipeline.models import (
    ACTION_CREATE_TEST,
    ACTION_NO_ACTION,
    INTENT_BUG_FIX,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    ActionDecision,
    ChangedSymbol,
    Intent,
)
from cta.llm.config import load_dotenv_into_env, make_embedding_client
from cta.sandbox.factory import choose_runner


def _pick(project, escalation_id: str | None) -> Escalation | None:
    pending = list_escalations(project)
    if not pending:
        print("대기 중인 사람 확인 항목 없음")
        return None
    if escalation_id:
        return get_escalation(project, escalation_id)
    if len(pending) == 1:
        print(f"사람 확인 항목이 1건이라 자동 선택: {pending[0].id}")
        return pending[0]
    print(f"사람 확인 항목이 {len(pending)}건이다 — id를 지정하라:")
    for e in pending:
        print(f"  {e.id}  [{e.kind}] {display_target(e.target)} — {e.reason}")
    return None


def _decision(args) -> str | None:
    if getattr(args, "as_intent", None):
        return "as"
    for name in ("intended", "test_issue", "proceed", "skip"):
        if getattr(args, name, False):
            return name.replace("_", "-")
    return None


def stated_intent_decision(escalation: Escalation, category: str) -> tuple[ActionDecision, str]:
    """사람이 지정한 의도로 규칙표를 다시 조회한다 (LLM 없음, R2).

    왜 필요한가: 의도 모름(ask)으로 멈춘 항목에 사람이 "이건 버그 수정이다"라고 답하면
    그 의도 × 저장된 테스트 상태로 규칙표를 다시 봐야 한다. 길은 여전히 규칙표가 정한다.
    입력: escalation 저장된 항목, category 사람이 지정한 의도(bug_fix/refactor/new_feature).
    출력: (규칙표 결정, 사용한 테스트 상태).
    구 파일(tests_status 없음)은 테스트 유무·실패 유무로 상태를 유추한다.
    """
    status = escalation.tests_status
    if not status:
        if not escalation.tests:
            status = TESTS_NONE
        else:
            status = TESTS_FAIL if escalation.failed_tests else TESTS_PASS
    change = ChangedSymbol(
        target=escalation.target,
        lines_added=0,
        lines_removed=0,
        signature_changed=False,
        diff_excerpt=escalation.diff_excerpt,
        file_rel=escalation.file_rel,
        change_line=escalation.change_line,
    )
    intent = Intent(
        category=category,
        analysis=escalation.analysis,
        confidence=1.0,
        evidence=(f"작성자 지정 의도: {category} (resolve --as)",) + tuple(escalation.evidence),
    )
    return decide(change, intent, status), status


def _resolve_as(project, escalation: Escalation, args) -> int:
    """--as 처리: 규칙표 재조회 → 할 일 없음 / 테스트 생성 / (리팩터링+실패) 선택지 안내."""
    category = args.as_intent
    decision, status = stated_intent_decision(escalation, category)
    label = INTENT_LABELS.get(category, category)
    print(f"\n{INDENT}{display_target(escalation.target)}  의도 지정: {label} → {decision.reason}")
    if decision.kind == ACTION_NO_ACTION:
        _remember(project, escalation, f"as:{category}", f"사람이 {label}으로 지정 — 할 일 없음")
        discard_escalation(project, escalation.id)
        print(f"{INDENT}할 일 없음 (기존 테스트 {status})")
        print(render_result_status(STATUS_OK))
        return 0
    if decision.kind != ACTION_CREATE_TEST:
        # 리팩터링인데 기존 테스트가 실패 중 — 기대값을 자동으로 고치지 않는다(R3)
        print(f"{INDENT}기존 테스트가 실패 중이라 사람 판단이 더 필요하다:")
        print(f"{INDENT}   · 일부러 동작을 바꾼 게 맞다 → cta resolve {escalation.id} --intended")
        print(f"{INDENT}   · 테스트 쪽 문제다           → cta resolve {escalation.id} --test-issue")
        return 1
    instruction = f"사람 판단: 이 변경은 {label}이다. {decision.briefing}"
    if args.hint:
        instruction += f"\n사람의 지시: {args.hint}"
    regression = None
    if category == INTENT_BUG_FIX and escalation.file_rel:
        # 버그 수정이면 maintain과 같은 보증 — 수정 전 코드에서 실패하는지 확인(SC-002 7단계)
        from cta.adapters.java.changes import GitChangeExtractor

        old = GitChangeExtractor(project, escalation.base).old_source(escalation.file_rel)
        if old is not None:
            regression = {escalation.file_rel: old}
    test_class = escalation.tests[0] if escalation.tests else None
    print(f"{INDENT}재개: {display_target(escalation.target)} — {label}으로 테스트 생성")
    outcome = run_generation(
        project_path=str(project.root),
        target=escalation.target,
        test_class=test_class,
        instruction_extra=instruction,
        fast=args.fast,
        ask_user=None if args.non_interactive else ask_on_terminal,
        regression_sources=regression,
        quiet=getattr(args, "quiet", False),
        runner_kind=choose_runner(getattr(args, "runner", None), args.fast),
        engine=getattr(args, "engine", ENGINE_LEGACY),
    )
    if outcome.get("status") == "error":
        print(f"오류: {outcome.get('report')}")
        return 1
    _remember(project, escalation, f"as:{category}", f"사람이 {label}으로 지정 — 테스트 생성")
    discard_escalation(project, escalation.id)
    if outcome.get("proposal"):
        print(f"{INDENT}다음: cta diff → 검토, cta apply {outcome['proposal']} → 반영")
    return EXIT_CODES[outcome["status_label"]]


def run_resolve(args: argparse.Namespace) -> int:
    load_dotenv_into_env()
    project = detect_maven_project(args.project)
    escalation = _pick(project, args.id)
    if escalation is None:
        return 1 if args.id else 0
    decision = _decision(args)
    if decision is None:
        shown = display_target(escalation.target)
        print(f"\n{INDENT}{shown}  [{escalation.kind}]  {escalation.reason}")
        for f in escalation.failed_tests:
            print(f"{INDENT}   · {f['name']}: 기대 {f['expected']}, 실제 {f['actual']}")
        print(
            f"{INDENT}결정을 지정하라: --intended | --test-issue | --proceed | --as <의도> | --skip"
            " (--hint 선택)"
        )
        return 1

    if decision == "as":
        return _resolve_as(project, escalation, args)

    failed_names = [f["name"] for f in escalation.failed_tests]
    if decision == "skip":
        _remember(project, escalation, decision, "사람이 건너뜀")
        discard_escalation(project, escalation.id)
        print(f"{INDENT}건너뜀 — 기록만 남김 ({escalation.id})")
        print(render_result_status(STATUS_OK))
        return 0

    if decision == "intended":
        instruction = (
            "사람 판단: 이번 변경은 일부러 동작을 바꾼 것이다. 실패한 테스트 "
            f"{', '.join(failed_names) or '(이름 미상)'}의 기대값을 새 동작 기준으로 수정하라. "
            "다른 테스트 메서드와 assert는 그대로 둔다."
        )
        note = "일부러 동작을 바꾼 것으로 확인 — 기대값을 새 기준으로 수정"
    elif decision == "test-issue":
        instruction = (
            "사람 판단: 테스트가 내부 구현에 너무 붙어 있다. 실패한 테스트 "
            f"{', '.join(failed_names) or '(이름 미상)'}를 동작(입출력) 기준으로 다시 작성하라. "
            "다른 테스트 메서드와 assert는 그대로 둔다."
        )
        note = "테스트 쪽 문제로 확인 — 실패 테스트를 동작 기준으로 재작성"
    else:  # proceed
        instruction = f"사람 판단: 계획대로 테스트를 만든다. {escalation.briefing}"
        note = "사람이 진행 결정"
    if args.hint:
        instruction += f"\n사람의 지시: {args.hint}"
        note += f" (힌트: {args.hint[:40]})"

    test_class = (
        escalation.failed_tests[0]["test_class"]
        if escalation.failed_tests
        else (escalation.tests[0] if escalation.tests else None)
    )
    print(f"\n{INDENT}재개: {display_target(escalation.target)} — {note}")
    outcome = run_generation(
        project_path=str(project.root),
        target=escalation.target,
        test_class=test_class,
        instruction_extra=instruction,
        fast=args.fast,
        ask_user=None if args.non_interactive else ask_on_terminal,
        authorized_tests=set(failed_names) if decision in ("intended", "test-issue") else None,
        quiet=getattr(args, "quiet", False),
        runner_kind=choose_runner(getattr(args, "runner", None), args.fast),
        engine=getattr(args, "engine", ENGINE_LEGACY),
    )
    if outcome.get("status") == "error":
        print(f"오류: {outcome.get('report')}")
        return 1
    _remember(project, escalation, decision, note)
    discard_escalation(project, escalation.id)
    if outcome.get("proposal"):
        print(f"{INDENT}다음: cta diff → 검토, cta apply {outcome['proposal']} → 반영")
    return EXIT_CODES[outcome["status_label"]]


def _remember(project, escalation: Escalation, decision: str, note: str) -> None:
    """판단 메모 저장 — 상황 요약(자연어)과 그 임베딩을 함께 남긴다(ADR-0026 D3).

    임베딩은 게이트웨이가 설정돼 있을 때만, 실패해도 메모는 저장한다(벡터 없이) — 사람의 결정을
    잃는 것이 임베딩 없는 것보다 나쁘다.
    """
    situation = situation_text(escalation.commit_message, escalation.target, escalation.analysis)
    embedding = None
    embedder = make_embedding_client()
    if embedder is not None:
        try:
            embedding = embedder[0].embed([situation], embedder[1])[0]
        except Exception as e:  # 참고 자료용 벡터 — 실패는 알리되 저장은 계속한다
            print(f"{INDENT}   (상황 임베딩 실패 — 벡터 없이 저장: {e})")
    save_memo(
        project,
        Memo(
            target=escalation.target,
            category=escalation.category,
            decision=decision,
            note=note,
            created_at=datetime.now().isoformat(timespec="seconds"),
            situation=situation,
            embedding=embedding,
        ),
    )
