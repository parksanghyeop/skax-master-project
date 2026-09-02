"""cta maintain — 변경 대응: 변경 추출 → 의도 분류(건별) → 규칙표 → 처리 (SC-002 / SC-003).

의도 분석 결과는 **변경 건마다 판단·확신도·근거·할 일을 전부 화면에 적는다** — 사용자가
왜 그 조치가 나왔는지 알 수 있어야 한다(ADR-0015 D2). create_test는 generate와 같은
경로(결과는 제안), escalate/ask는 저장 후 멈춤(cta resolve로 재개). 층: cli(조립).
"""

from cta.adapters.java.changes import GitChangeExtractor, ReferencingTestLocator
from cta.adapters.java.failures import parse_failed_tests
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.runner import JavaTestRunner
from cta.cli.escalations import Escalation, make_id, save_escalation
from cta.cli.generate import CACHE_DIR_NAME, ask_on_terminal, ensure_prepared, run_generation
from cta.cli.graph_access import FALLBACK_NOTE, GRAPH_NOTE, try_open_store
from cta.cli.memos import find_similar, render_memos
from cta.cli.render import (
    EXIT_CODES,
    INDENT,
    STATUS_HUMAN,
    STATUS_OK,
    STATUS_QUALITY,
    box,
    circled,
    display_target,
    render_analysis,
    render_diff_excerpt,
    render_result_status,
)
from cta.core.pipeline.maintain import ChangeAnalysis, analyze_changes
from cta.core.pipeline.models import (
    ACTION_ASK,
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    INTENT_BUG_FIX,
    TESTS_FAIL,
)
from cta.graph.model import EDGE_COVERS
from cta.llm.config import load_dotenv_into_env, make_llm_client
from cta.llm.intent import PromptedIntentClassifier
from cta.llm.metering import MeteredClient
from cta.sandbox.docker_sandbox import DockerSandbox


class GraphTestLocator:
    """그래프의 실측 COVERS로 검증 테스트를 찾는다 (TestLocator 구현)."""

    def __init__(self, store, project_key: str) -> None:
        self._store = store
        self._project_key = project_key

    def find(self, target: str) -> list[str]:
        tests = self._store.neighbors(self._project_key, target, EDGE_COVERS, "in")
        return sorted({t.key for t in tests})

    def close(self) -> None:
        self._store.close()


def _make_locator(project):
    """그래프가 있으면 실측, 없으면 소스 참조 파싱 폴백 — 어느 쪽인지 화면에 알린다."""
    store = try_open_store(str(project.root))
    if store is None:
        return ReferencingTestLocator(project), FALLBACK_NOTE
    return GraphTestLocator(store, str(project.root)), GRAPH_NOTE


def run_maintain(args) -> int:
    load_dotenv_into_env()
    project = detect_maven_project(args.project)
    extractor = GitChangeExtractor(project, args.diff)

    # 1단계: 변경 추출 (일반 코드) — 시그니처·접근 제어자·줄 수·커밋 메시지·이슈 번호 단서 포함
    change_set = extractor.extract()
    if not change_set.symbols:
        print("변경 없음 — 할 일이 없다")
        print(render_result_status(STATUS_OK))
        return 0
    message = change_set.commit_message.strip().splitlines()[0] if change_set.commit_message else ""
    header = f"변경 {len(change_set.symbols)}건 확인  (비교 기준: {args.diff}"
    header += f', 커밋 메시지: "{message}")' if message else ", 미커밋 변경)"
    print(f"\n{INDENT}{header}")

    # 2~4단계: 건별 의도 분류(LLM) → 기존 테스트 실행 → 규칙표
    raw_client, model = make_llm_client()
    client = MeteredClient(raw_client)
    classifier = PromptedIntentClassifier(client, model)
    locator, locator_note = _make_locator(project)
    print(f"{INDENT}기존 테스트 찾기: {locator_note}\n")
    sandbox = DockerSandbox()
    cache_dir = project.root / CACHE_DIR_NAME
    runner = JavaTestRunner(project, sandbox, cache_dir)
    problem = ensure_prepared(project, runner, cache_dir, None)
    if problem:
        print(f"오류: {problem}")
        return 1

    def memo_lookup(target: str) -> str:
        return render_memos(find_similar(project, target))

    def progress(msg: str) -> None:
        print(f"{INDENT}      … {msg}", flush=True)

    try:
        analyses = analyze_changes(change_set, classifier, locator, runner, memo_lookup, progress)
    finally:
        if hasattr(locator, "close"):
            locator.close()

    for i, analysis in enumerate(analyses, 1):
        print(render_analysis(i, analysis))
        print()

    if args.plan_only:
        print(f"{INDENT}(--plan-only: 판단만 출력하고 처리하지 않았다)")
        print(render_result_status(STATUS_OK))
        return 0

    # 5단계: 처리 — create_test는 생성(제안), escalate/ask는 저장 후 멈춤
    outcomes: list[dict] = []
    escalations: list[str] = []
    untouched = 0
    for i, analysis in enumerate(analyses, 1):
        kind = analysis.decision.kind
        if kind == ACTION_CREATE_TEST:
            print(f"{INDENT}{circled(i)} 처리 — {display_target(analysis.change.target)}")
            outcome = _create_test(project, extractor, change_set, analysis, args)
            outcomes.append(outcome)
        elif kind in (ACTION_ESCALATE, ACTION_ASK):
            escalation = _save_escalation(project, extractor, change_set, analysis)
            escalations.append(escalation.id)
            print(_render_escalation(i, analysis, escalation))
        else:
            untouched += 1

    print(f"\n{INDENT}품질 확인")
    weakened = [
        r for o in outcomes for n, p, r in o.get("gate_results", []) if n == "assert" and not p
    ]
    print(
        f"{INDENT}   기존 테스트 조건 느슨해짐   {'없음' if not weakened else '있음 — 사람 확인'}"
    )
    for o in outcomes:
        before, after = o.get("mutation_before"), o.get("mutation_after")
        if before or after:
            from cta.cli.generate import _score_text

            print(f"{INDENT}   버그 검출력                 {_score_text(before, after)}")
    print()
    for o in outcomes:
        if o.get("proposal"):
            file_name = o["test_rel"].rsplit("/", 1)[-1]
            print(
                f"{INDENT}수정됨       {file_name} (+{o.get('new_tests', 0)})"
                f"  → 제안 {o['proposal']!r}: cta diff / cta apply"
            )
    print(f"{INDENT}손대지 않음  {untouched}건")
    print(f"{INDENT}사람 확인    {len(escalations)}건")
    if escalations:
        options = "--intended | --test-issue | --proceed | --skip"
        print(f"{INDENT}판단 전달    cta resolve {escalations[0]} {options}")
    print(f"{INDENT}소요 토큰    {client.total_tokens:,}")

    if escalations:
        status = STATUS_HUMAN
    elif any(o.get("status") not in ("accepted", None) for o in outcomes):
        status = STATUS_QUALITY
    else:
        status = STATUS_OK
    print(render_result_status(status))
    return EXIT_CODES[status]


def _create_test(project, extractor, change_set, analysis: ChangeAnalysis, args) -> dict:
    """재발 방지(또는 기능) 테스트 생성 — bug_fix면 수정 전 코드 검증 게이트를 붙인다."""
    is_bug_fix = analysis.intent.category == INTENT_BUG_FIX
    regression = extractor.old_main_sources(change_set) if is_bug_fix else None
    # 검증 테스트 클래스가 있으면 거기에 추가한다(SC-002 "OrderServiceTest.java (+1)")
    test_class = analysis.tests[0] if analysis.tests else None
    outcome = run_generation(
        project_path=str(project.root),
        target=analysis.change.target,
        test_class=test_class,
        instruction_extra=analysis.decision.briefing.replace("\n", " "),
        fast=args.fast,
        ask_user=None if args.non_interactive else ask_on_terminal,
        regression_sources=regression,
        measure_before=not args.fast,
    )
    if outcome.get("status") == "error":
        print(f"{INDENT}   오류: {outcome.get('report')}")
    if is_bug_fix and outcome.get("gate_results"):
        verdict = next((p for n, p, _ in outcome["gate_results"] if n == "regression"), None)
        if verdict is not None:
            answer = "실패함 (정상)" if verdict else "통과함 → 무효, 다시 만듦"
            print(f"{INDENT}   확인: 수정 전 코드에서 실패하는가? → {answer}")
    return outcome


def _save_escalation(project, extractor, change_set, analysis: ChangeAnalysis) -> Escalation:
    failed = [
        {
            "name": f.name,
            "test_class": f.test_class,
            "expected": f.expected,
            "actual": f.actual,
            "message": f.message,
        }
        for f in parse_failed_tests(analysis.run_summary)
    ]
    from datetime import datetime

    escalation = Escalation(
        id=make_id(analysis.change.target),
        kind=analysis.decision.kind,
        target=analysis.change.target,
        category=analysis.intent.category,
        confidence=analysis.intent.confidence,
        evidence=list(analysis.intent.evidence),
        analysis=analysis.intent.analysis,
        reason=analysis.decision.reason,
        briefing=analysis.decision.briefing,
        tests=list(analysis.tests),
        run_summary=analysis.run_summary,
        failed_tests=failed,
        file_rel=analysis.change.file_rel,
        change_line=analysis.change.change_line,
        diff_excerpt=analysis.change.diff_excerpt,
        base=extractor.base,
        commit_message=change_set.commit_message,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    save_escalation(project, escalation)
    return escalation


def _render_escalation(index: int, analysis: ChangeAnalysis, esc: Escalation) -> str:
    """사람 확인 상자(SC-003) — 실패 테스트, 확인해 보실 곳, 선택지, 재개 명령.

    종류(escalate/ask)와 무관하게 기존 테스트가 깨진 상태면 실패 상세와 의심 위치를
    보여준다 — 사람이 판단하려면 "무엇이 어떻게 깨졌나"가 반드시 필요하다.
    """
    tests_failed = analysis.tests_status == TESTS_FAIL
    lines = []
    if tests_failed:
        lines.append(f"{INDENT}영향 테스트 실행 → {_failure_count(analysis, esc)}\n")
    if esc.kind == ACTION_ESCALATE:
        lines.append(box("사람 확인 필요 — 자동으로 고치지 않았습니다"))
        lines.append(f"\n{INDENT} 동작이 안 바뀌어야 하는 변경인데 테스트가 깨졌습니다.\n")
    else:
        lines.append(box("사람에게 질문 — 추측으로 진행하지 않았습니다"))
        lines.append(f"\n{INDENT} {display_target(esc.target)}: {esc.reason}\n")
    if tests_failed:
        lines.append(f"{INDENT}   (A) 이번 수정에 진짜 버그가 있다          ← 가능성 높음")
        lines.append(f"{INDENT}   (B) 테스트가 내부 구현에 너무 붙어 있다\n")
        lines.append(f"{INDENT} 실패한 테스트")
        for f in esc.failed_tests or [
            {"name": "(이름 파싱 실패 — 실행 요약 참조)", "expected": "", "actual": ""}
        ]:
            detail = (
                f"기대 {f['expected']}, 실제 {f['actual']}"
                if f.get("expected") or f.get("actual")
                else f.get("message", "")
            )
            lines.append(f"{INDENT}   · {f['name']:<40} {detail}")
        lines.append(f"\n{INDENT} 확인해 보실 곳")
        lines.append(f"{INDENT}   {esc.file_rel.rsplit('/', 1)[-1]} {esc.change_line}행 부근")
        for ln in render_diff_excerpt(esc.diff_excerpt):
            lines.append(f"{INDENT}     {ln}")
        lines.append(f"\n{INDENT} 수정한 테스트   0건 (일부러 안 함)")
    lines.append(f"{INDENT} 사람 확인 필요  1건\n")
    lines.append(f"{INDENT} 판단을 알려주시면 이어서 진행합니다")
    if tests_failed:
        lines.append(f"{INDENT}   · 일부러 동작을 바꾼 게 맞다  → cta resolve {esc.id} --intended")
        lines.append(
            f"{INDENT}   · 테스트 쪽 문제다            → cta resolve {esc.id} --test-issue"
        )
        lines.append(f"{INDENT}   · 코드를 직접 고쳤다          → 다시 cta maintain")
    else:
        lines.append(f"{INDENT}   · 테스트를 만들어도 된다      → cta resolve {esc.id} --proceed")
    lines.append(f"{INDENT}   · 이번엔 건너뛴다            → cta resolve {esc.id} --skip")
    lines.append("")
    return "\n".join(lines)


def _failure_count(analysis: ChangeAnalysis, esc: Escalation) -> str:
    from cta.adapters.java.failures import count_tests_run

    total = count_tests_run(analysis.run_summary)
    failed = len(esc.failed_tests)
    if total:
        return f"{total}건 중 {failed}건 실패"
    return f"{failed}건 실패"
