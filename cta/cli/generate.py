"""cta generate — 클래스의 테스트 없는 메서드들에 테스트를 만들어 '제안'으로 보관한다 (SC-001).

흐름(시나리오 4단계 그대로 출력):
  [1/4] 재료 수집 — 메서드 선정 + 확인 항목(분기·경계값·예외·null) 열거
  [2/4] 파라미터 객체 만드는 법 확인 — 직접 생성 / builder / mock
  [3/4] 테스트 작성 — LLM 생성 → 컴파일 → 방금 만든 테스트만 실행, 실패하면 반복(최대 8회)
  [4/4] 품질 확인 — 확인 항목 충족(JaCoCo), 버그 검출력(PIT), 기준 낮춤 여부(assert·skip)
생성물은 소스 트리에 남지 않는다 — 검토(cta diff)·반영(cta apply)은 사용자 몫
(v4 Step 3). 변경 대응(maintain)·판단 전달(resolve)도 같은 run_generation을 쓴다. 층: cli.
"""

import time
import uuid
from collections.abc import Callable
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from cta.adapters.java.failures import count_tests_run, describe_attempt
from cta.adapters.java.gates import (
    AssertIntegrityGate,
    CoverageGate,
    FileScopeGate,
    SkipAnnotationGate,
    snapshot_baseline,
)
from cta.adapters.java.inspector import JavaSourceInspector
from cta.adapters.java.materials import (
    KINDS,
    check_item_satisfaction,
    collect_materials,
    locate_test_file,
    render_materials,
    select_methods,
)
from cta.adapters.java.maven import MavenProject, detect_maven_project, find_existing_test_class
from cta.adapters.java.mutation import MutationGate, measure_mutation
from cta.adapters.java.parsing import find_class_file, parse_methods, parse_target
from cta.adapters.java.quality import AssertCountChecker
from cta.adapters.java.regression import BugReproductionGate
from cta.adapters.java.runner import JavaTestRunner
from cta.adapters.java.skills.select import render_skills, select_skills, signals_from
from cta.adapters.java.writer import JavaTestWriter
from cta.cli.graph_access import choose_code_graph
from cta.cli.proposals import STATUS_ACCEPTED, STATUS_NEEDS_REVIEW, save_proposal
from cta.cli.render import (
    INDENT,
    STATUS_ERROR,
    STATUS_HUMAN,
    STATUS_OK,
    STATUS_QUALITY,
    format_duration,
    format_tokens,
)
from cta.core.config import load_config
from cta.core.ports import UserReply
from cta.core.submit import generate_with_gates
from cta.core.writer_graph import (
    InterruptUserGate,
    WriterPorts,
    build_writer_graph,
    invoke_with_interrupts,
)
from cta.llm.config import make_llm_client
from cta.llm.generation import PromptedGenerator
from cta.llm.metering import MeteredClient
from cta.sandbox.factory import LOCAL_MODE_WARNING, RUNNER_DOCKER, RUNNER_LOCAL, make_sandbox

# 준비 단계에서 만드는 의존성 캐시 위치 — 대상 프로젝트 밑에 두어 지우기 쉽게 한다.
CACHE_DIR_NAME = ".cta/m2repo"

# --max-methods 기본값 — 시나리오 SC-001의 입력 예시(4). 한 번의 생성이 너무 길어지지 않게.
DEFAULT_MAX_METHODS = 4

# 작성 프롬프트 [프로젝트 관례]의 기본 문장. 스킬(ADR-0017)이 선택되면 그 뒤에 본문이 붙는다.
# 이 문장은 저장된 LLM 호출 기록과 맞물려 있다 — 바꾸면 기록을 다시 만든다.
BASE_STYLE_NOTE = "프로젝트의 기존 테스트 스타일(이름 규칙, import 방식, mock 사용법)을 따른다."

# SubmitResult.status → 화면의 결과 상태
_STATUS_LABEL = {
    "accepted": STATUS_OK,
    "human_review": STATUS_QUALITY,  # 게이트 재시도 소진 — SC-004 "결과 상태: 품질 미달"
    "not_passed": STATUS_HUMAN,  # 에이전트가 한계 보고로 끝냄 — 사람이 봐야 한다
    "error": STATUS_ERROR,
}


def default_test_class(class_name: str) -> str:
    """--test-class 생략 시 이름 규칙: OrderService → OrderServiceTest (클래스당 하나, ADR-0015)."""
    return f"{class_name}Test"


def ask_on_terminal(question: str) -> UserReply:
    """반복 중 멈춤 지점의 터미널 응답기 — 계속/중지/힌트를 stdin으로 받는다."""
    print(f"\n[일시정지] 에이전트가 묻습니다:\n{question}")
    # lstrip("﻿"): Windows에서 파이프로 답을 넣으면 BOM이 붙을 수 있다
    raw = input("답 [Enter=계속 / s=중지 / 그 외 입력=힌트로 전달하고 계속]: ").lstrip("﻿").strip()
    if raw.lower() == "s":
        return UserReply(action="stop")
    return UserReply(action="continue", hint=raw)


def ensure_prepared(
    project: MavenProject, runner: JavaTestRunner, cache_dir: Path, warmup_test: str | None
) -> str | None:
    """의존성 캐시가 없으면 준비 단계(최초 1회)를 돌린다. 실패하면 사유, 성공·불필요면 None."""
    if cache_dir.is_dir():
        return None
    warmup = warmup_test or find_existing_test_class(project)
    if not warmup:
        return "준비 단계에 예열할 기존 테스트가 없다"
    print(f"{INDENT}[준비] 의존성 다운로드 + 예열({warmup}) — 최초 1회, 수 분 걸릴 수 있다...")
    prepared = runner.prepare(warmup)
    if prepared.exit_code != 0:
        return f"준비 실패 (exit {prepared.exit_code})\n{prepared.output[-2000:]}"
    return None


def run_generation(
    project_path: str,
    target: str,
    test_class: str | None = None,
    instruction_extra: str = "",
    model_override: str | None = None,
    warmup_test: str | None = None,
    fast: bool = False,
    ask_user: Callable[[str], UserReply] | None = None,
    max_methods: int | None = DEFAULT_MAX_METHODS,
    include_all: bool = False,
    regression_sources: dict[str, str | None] | None = None,
    authorized_tests: set[str] | None = None,
    measure_before: bool = False,
    quiet: bool = False,
    runner_kind: str = RUNNER_DOCKER,
) -> dict:
    """재료 수집→생성→게이트→제안 저장까지 수행한다. generate/maintain/resolve/eval 공용 진입점.

    입력: target "Class" 또는 "Class#m1,m2"(지정 메서드만). max_methods는 미지정 시 선정 상한.
      regression_sources — bug_fix일 때 수정 전 소스({상대경로: 내용}) → 게이트 ⑥ 부착.
      authorized_tests — 사람이 고쳐도 된다고 지정한 테스트 메서드(assert 게이트 제외 목록).
      measure_before — 생성 전 기존 테스트의 버그 검출력을 먼저 재서 전후 비교(SC-002).
      quiet — 경과 시간이 붙는 진행 줄(`[ 113초] …`)을 끈다. CI 로그용(--quiet).
      runner_kind — "docker"(격리, 기본) 또는 "local"(이 PC의 Maven·JDK, 준비 단계 없음, ADR-0019).
    설정: 프로젝트 루트의 cta.toml(core/config.py) — 게이트 기준치·반복 상한·시간 초과·모델·예산.
    출력 dict: status(accepted/human_review/not_passed/error), status_label, proposal, attempts,
      writer_attempts, elapsed, tokens, test_rel, test_class, gate_results, failure_reasons,
      report, model, tests_run, new_tests, check_total, check_satisfied, mutation_before/after.
    """
    started = time.monotonic()
    project = detect_maven_project(project_path)
    config = load_config(project.root)
    raw_client, model = make_llm_client(
        model_default=config.model, timeout_default=config.gateway_timeout_sec
    )
    client = MeteredClient(raw_client, max_tokens=config.max_tokens_per_run)
    if model_override:
        model = model_override

    class_name, method_field = parse_target(target)
    class_file = find_class_file(project, class_name)
    if class_file is None:
        return _error(f"클래스 {class_name!r}를 찾지 못했다")
    only = parse_methods(method_field) or None
    methods, skipped = select_methods(
        project,
        class_file,
        max_methods if only is None else None,
        only=only,
        include_all=include_all,
    )
    test_class = test_class or default_test_class(class_name)
    materials = collect_materials(project, class_file, methods, skipped, test_class)
    package = materials.package
    test_path = locate_test_file(project, package, test_class)
    test_rel = test_path.relative_to(project.root).as_posix()
    fq = f"{package}.{{}}" if package else "{}"

    print(f"\n{INDENT}대상: {fq.format(class_name)}\n")
    print(f"{INDENT}[1/4] 재료 수집")
    for name, why in skipped:
        print(f"{INDENT}      건너뜀 {class_name}.{name} — {why}")
    if not methods:
        print(f"{INDENT}      테스트 만들 메서드가 없다 (전부 강제하려면 --all)")
        return _error("테스트 만들 메서드가 없다")
    names = ", ".join(m.name for m in methods)
    print(f"{INDENT}      테스트 만들 메서드 {len(methods)}개 선정: {names}")
    counts = materials.count_by_kind()
    breakdown = ", ".join(f"{k} {counts[k]}" for k in KINDS)
    print(f"{INDENT}      확인해야 할 항목 {len(materials.check_items)}개 ({breakdown})")

    print(f"\n{INDENT}[2/4] 파라미터 객체 만드는 법 확인")
    if not materials.constructions:
        print(f"{INDENT}      파라미터·의존 객체 없음")
    for hint in materials.constructions:
        print(f"{INDENT}      {hint.type_name:<16}→ {hint.strategy} ({hint.reason})")
    existing_tests = materials.existing_test_code.count("@Test")
    if materials.existing_test_code:
        print(
            f"{INDENT}      기존 테스트 파일 있음 → {test_class}에 메서드 추가 "
            f"(기존 {existing_tests}개 유지)"
        )
    # 스킬 선택(ADR-0017) — 재료·실행 종류라는 이미 결정된 신호로 규칙표 조회. 어떤 신호가 어떤
    # 스킬을 붙였는지 화면에 남긴다(산출물 "스킬 선택 로그")
    skills = select_skills(signals_from(materials, regression_sources, authorized_tests))
    skill_names = [s.name for s in skills]
    print(f"{INDENT}      적용 스킬: {', '.join(skill_names) if skill_names else '없음'}")

    sandbox = make_sandbox(runner_kind)
    cache_dir = project.root / CACHE_DIR_NAME
    runner = JavaTestRunner(project, sandbox, cache_dir)
    if runner_kind == RUNNER_LOCAL:
        # 로컬 모드는 준비 단계(의존성 캐시·예열)가 없다 — 사용자의 ~/.m2를 그대로 쓴다
        print(f"{INDENT}      [!] {LOCAL_MODE_WARNING}")
    else:
        problem = ensure_prepared(project, runner, cache_dir, warmup_test)
        if problem:
            return _error(problem)

    baseline = snapshot_baseline(project)  # 게이트 기준선 — 생성 시작 전에 뜬다
    method_names = {m.name for m in methods}

    mutation_before: tuple[int, int] | None = None
    if measure_before and materials.existing_test_code and not fast:
        print(f"\n{INDENT}      기존 테스트의 버그 검출력 측정 중 (전후 비교용)...")
        measured = measure_mutation(
            project, sandbox, cache_dir, fq.format(class_name), fq.format(test_class), method_names
        )
        if measured:
            mutation_before = (measured[0], measured[1])

    # 게이트 인스턴스는 호출마다 새로 만들되, 마지막 것의 실측(라인 커버리지·검출률)을 화면에 쓴다
    last_gates: dict[str, object] = {}

    def make_gates():
        gates = [
            AssertIntegrityGate(project, baseline, authorized_tests),
            SkipAnnotationGate(project, baseline),
            FileScopeGate(project, baseline, allowed={test_rel}),
        ]
        if regression_sources is not None:
            gates.append(BugReproductionGate(project, runner, regression_sources, test_class))
        if fast:
            return gates
        coverage = CoverageGate(
            project,
            sandbox,
            cache_dir,
            test_class,
            f"{class_name}.java",
            materials.target_lines,
            config.gates,
        )
        mutation = MutationGate(
            project,
            sandbox,
            cache_dir,
            fq.format(class_name),
            fq.format(test_class),
            config.gates.mutation_min,
            target_methods=method_names,
        )
        last_gates["coverage"] = coverage
        last_gates["mutation"] = mutation
        return gates + [coverage, mutation]

    instruction = (
        f"{class_name}의 메서드 {names}에 대한 테스트를 만들라. "
        f"테스트 클래스 이름은 {test_class}, 패키지는 {package or '(기본 패키지)'}. "
        "확인해야 할 항목마다 테스트 메서드를 하나씩 두고, 기존 테스트 파일이 있으면 "
        "기존 테스트 메서드와 assert는 그대로 둔 채 새 메서드만 추가한다."
    )
    if instruction_extra:
        instruction += f"\n추가 지침: {instruction_extra}"

    def progress(message: str) -> None:
        """진행 한 줄 출력 — 경과 시간을 붙여 어디서 오래 걸리는지 보이게 한다. --quiet면 무음."""
        if quiet:
            return
        print(f"{INDENT}      [{time.monotonic() - started:4.0f}초] {message}", flush=True)

    code_graph, graph_note, graph_store = choose_code_graph(project)
    print(f"{INDENT}      유사 테스트 검색: {graph_note}")
    ports = WriterPorts(
        inspector=JavaSourceInspector(project),
        graph=code_graph,
        writer=JavaTestWriter(project, sandbox, cache_dir),
        runner=runner,
        checker=AssertCountChecker(project),
        gate=InterruptUserGate(),
        generator=PromptedGenerator(
            client,
            model,
            "Java",
            "JUnit 5",
            "\n\n".join([BASE_STYLE_NOTE, render_skills(skills)]) if skills else BASE_STYLE_NOTE,
        ),
        progress=progress,
    )
    app = build_writer_graph(
        ports,
        checkpointer=MemorySaver(),
        ask_every=config.retry.ask_every,
        max_total=config.retry.max_total,
    )
    ask = ask_user or (lambda q: UserReply(action="continue"))
    extra_context = render_materials(materials)
    graph_target = f"{class_name}#{','.join(m.name for m in methods)}"

    def run_writer(state):
        return invoke_with_interrupts(app, state, thread_id=str(uuid.uuid4()), ask_user=ask)

    def make_state(current_instruction: str):
        return {
            "instruction": current_instruction,
            "target": graph_target,
            "test_path": str(test_path),
            "selector": test_class,
            "context": "",
            "test_code": "",
            "write_result": "",
            "last_run": "",
            "prev_run": "",
            "attempts": 0,
            "quality": "",
            "report": "",
            "status": "working",
            "extra_context": extra_context,
            "history": [],
        }

    print(f"\n{INDENT}[3/4] 테스트 작성  (모델: {model}, 실행: {runner_kind}, 결과: {test_rel})")
    try:
        result = generate_with_gates(
            run_writer=run_writer,
            make_state=make_state,
            make_gates=make_gates,
            base_instruction=instruction,
            max_retries=config.gates.max_retries,
            progress=progress,
        )
    except BaseException:
        # 도중에 죽어도(게이트웨이 시간 초과, Ctrl+C, Docker 오류) 생성물이 소스 트리에 남으면
        # 안 된다 — 기존 파일은 원문으로, 새 파일은 삭제로 되돌린다(v4 Step 3: 반영은 apply만)
        _restore_test_file(test_path, materials.existing_test_code)
        raise
    finally:
        if graph_store is not None:
            graph_store.close()
    history = result.final_state.get("history") or []
    for entry in history:
        summary = describe_attempt(entry.get("write_result", ""), entry.get("run_result", ""))
        print(f"{INDENT}      {entry.get('attempt', '?')}차  {summary}")
    if result.status == "not_passed":
        print(
            f"{INDENT}      한계 보고: {result.final_state.get('report', '').splitlines()[0][:80]}"
        )

    gate_results = [
        (g.name, g.passed, g.reason)
        for g in (result.gate_report.results if result.gate_report else [])
    ]
    print(f"\n{INDENT}[4/4] 품질 확인")
    check_total = len(materials.check_items)
    check_satisfied = None
    coverage_gate = last_gates.get("coverage")
    if coverage_gate is not None and getattr(coverage_gate, "last_lines", None):
        check_satisfied = check_item_satisfaction(materials.check_items, coverage_gate.last_lines)
        pct = f"({check_satisfied / check_total:.0%})" if check_total else ""
        print(f"{INDENT}      확인 항목 충족   {check_satisfied} / {check_total}  {pct}")
    else:
        print(f"{INDENT}      확인 항목 충족   측정 안 함 (--fast 또는 실행 실패)")
    mutation_gate = last_gates.get("mutation")
    mutation_after = getattr(mutation_gate, "last_score", None) if mutation_gate else None
    print(f"{INDENT}      버그 검출력      {_score_text(mutation_before, mutation_after)}")
    weakened = [r for n, p, r in gate_results if n in ("assert", "skip") and not p]
    lowered = "없음" if not weakened else "있음 — " + weakened[0].splitlines()[0]
    print(f"{INDENT}      기준 낮춤 여부   {lowered}")
    for name, passed, reason in gate_results:
        verdict = "통과" if passed else "탈락"
        print(f"{INDENT}      게이트[{name}] {verdict} — {reason.splitlines()[0]}")

    # 생성물을 제안으로 옮기고 소스 트리는 원상 복구 — 반영은 apply만 한다(v4 Step 3)
    proposal_name = None
    generated = ""
    if test_path.is_file():
        generated = test_path.read_text(encoding="utf-8")
        if materials.existing_test_code:
            test_path.write_text(materials.existing_test_code, encoding="utf-8")
        else:
            test_path.unlink()
        if result.status in ("accepted", "human_review"):
            status = STATUS_ACCEPTED if result.status == "accepted" else STATUS_NEEDS_REVIEW
            save_proposal(
                project,
                test_class,
                target,
                test_rel,
                generated,
                status,
                [
                    f"[{n}] {'통과' if p else '탈락'} — {r.splitlines()[0]}"
                    for n, p, r in gate_results
                ],
            )
            proposal_name = test_class

    elapsed = time.monotonic() - started
    tests_run = count_tests_run(result.final_state.get("last_run", ""))
    new_tests = max(0, generated.count("@Test") - existing_tests) if generated else 0
    status_label = _STATUS_LABEL.get(result.status, STATUS_ERROR)
    print()
    if proposal_name:
        verb = "수정됨" if materials.existing_test_code else "생성됨"
        print(f"{INDENT}{verb:<8} {test_rel}  (+{new_tests} 테스트, 제안 {proposal_name!r})")
        run_state = "전체 통과" if result.final_state.get("status") == "passed" else "실패"
        print(f"{INDENT}테스트   {tests_run}개 / {run_state}")
    print(f"{INDENT}소요     {format_duration(elapsed)} · {format_tokens(client.total_tokens)}")
    print(f"\n{INDENT}결과 상태: {status_label}")

    return {
        "status": result.status,
        "status_label": status_label,
        "proposal": proposal_name,
        "attempts": result.attempts,
        "writer_attempts": result.final_state.get("attempts", 0),
        "elapsed": elapsed,
        "tokens": client.total_tokens,
        "test_rel": test_rel,
        "test_class": test_class,
        "gate_results": gate_results,
        "failure_reasons": result.gate_report.failure_reasons if result.gate_report else "",
        "report": result.final_state.get("report", ""),
        "model": model,
        "tests_run": tests_run,
        "new_tests": new_tests,
        "check_total": check_total,
        "check_satisfied": check_satisfied,
        "mutation_before": mutation_before,
        "mutation_after": mutation_after,
        "skills": skill_names,
        "runner": runner_kind,
    }


def _restore_test_file(test_path: Path, original: str) -> None:
    """생성 도중 바뀐 테스트 파일을 원래대로 — 원문이 있으면 되돌리고, 새 파일이면 지운다."""
    if original:
        test_path.write_text(original, encoding="utf-8")
    else:
        test_path.unlink(missing_ok=True)


def _error(message: str) -> dict:
    return {"status": "error", "status_label": STATUS_ERROR, "report": message, "proposal": None}


def _score_text(before: tuple[int, int] | None, after: tuple[int, int] | None) -> str:
    def pct(score: tuple[int, int] | None) -> str:
        if not score or score[1] == 0:
            return "측정 안 함"
        return f"{score[0] / score[1]:.0%}"

    if before:
        return f"{pct(before)} → {pct(after)}"
    return pct(after)
