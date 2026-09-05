"""cta resolve — 판단 전달: 저장된 사람 확인 항목을 읽어 멈춘 지점부터 이어서 실행 (SC-003 8단계).

선택지(사람이 명시적으로 고른 것만 실행한다 — R3는 '사람 확인 없는' 갱신을 막는 규칙):
  --intended    일부러 동작을 바꾼 게 맞다 → 실패한 테스트의 기대값을 새 동작 기준으로 수정
  --test-issue  테스트 쪽 문제다 → 실패한 테스트를 동작(입출력) 기준으로 다시 작성
  --proceed     (질문 항목) 계획대로 테스트 생성 (--hint로 지시 추가)
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
from cta.cli.memos import Memo, save_memo
from cta.cli.render import EXIT_CODES, INDENT, STATUS_OK, display_target, render_result_status
from cta.llm.config import load_dotenv_into_env
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
    for name in ("intended", "test_issue", "proceed", "skip"):
        if getattr(args, name, False):
            return name.replace("_", "-")
    return None


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
            f"{INDENT}결정을 지정하라: --intended | --test-issue | --proceed | --skip (--hint 선택)"
        )
        return 1

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
    save_memo(
        project,
        Memo(
            target=escalation.target,
            category=escalation.category,
            decision=decision,
            note=note,
            created_at=datetime.now().isoformat(timespec="seconds"),
        ),
    )
