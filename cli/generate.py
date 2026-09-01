"""cta generate — 대상 메서드에 새 테스트를 생성해 '제안'으로 보관한다.

흐름: 준비(캐시) → 기준선 스냅샷 → [생성 → 게이트 5종] 루프 → **제안 저장**.
생성물은 소스 트리에 남지 않는다 — 검토(cta diff)·반영(cta apply)은 사용자 몫
(v4 Step 3: 변경은 즉시 반영되지 않는다). 층: cli(조립).
"""

import time
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from adapters.java.gates import (
    AssertIntegrityGate,
    CoverageGate,
    FileScopeGate,
    SkipAnnotationGate,
    snapshot_baseline,
)
from adapters.java.inspector import JavaSourceInspector
from adapters.java.maven import detect_maven_project, find_existing_test_class
from adapters.java.mutation import MutationGate
from adapters.java.parsing import find_class_file, method_line_spans, parse_target, read_package
from adapters.java.quality import AssertCountChecker
from adapters.java.runner import JavaTestRunner
from adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph
from adapters.java.writer import JavaTestWriter
from cli.proposals import STATUS_ACCEPTED, STATUS_NEEDS_REVIEW, save_proposal
from core.gates import load_gate_config
from core.ports import UserReply
from core.submit import generate_with_gates
from core.writer_graph import (
    InterruptUserGate,
    WriterPorts,
    build_writer_graph,
    invoke_with_interrupts,
)
from llm.config import make_llm_client
from llm.generation import PromptedGenerator
from sandbox.docker_sandbox import DockerSandbox

# 준비 단계에서 만드는 의존성 캐시 위치 — 대상 프로젝트 밑에 두어 지우기 쉽게 한다.
CACHE_DIR_NAME = ".cta/m2repo"


def default_test_class(class_name: str, method_name: str) -> str:
    """--test-class 생략 시 이름 규칙: Calculator#divide → CalculatorDivideTest."""
    suffix = method_name[:1].upper() + method_name[1:] if method_name else "Generated"
    return f"{class_name}{suffix}Test"


def ask_on_terminal(question: str) -> UserReply:
    """반복 중 멈춤 지점의 터미널 응답기 — 계속/중지/힌트를 stdin으로 받는다."""
    print(f"\n[일시정지] 에이전트가 묻습니다:\n{question}")
    # lstrip("﻿"): Windows에서 파이프로 답을 넣으면 BOM이 붙을 수 있다
    raw = input("답 [Enter=계속 / s=중지 / 그 외 입력=힌트로 전달하고 계속]: ").lstrip("﻿").strip()
    if raw.lower() == "s":
        return UserReply(action="stop")
    return UserReply(action="continue", hint=raw)


def run_generation(
    project_path: str,
    target: str,
    test_class: str | None = None,
    instruction_extra: str = "",
    model_override: str | None = None,
    warmup_test: str | None = None,
    fast: bool = False,
    ask_user=None,
) -> dict:
    """생성→게이트→제안 저장까지 수행한다. CLI와 평가 하네스가 공유하는 진입점.

    출력 dict: status(accepted/human_review/not_passed/error), proposal(제안 이름
    또는 None), attempts, writer_attempts, elapsed, test_rel, gate_results,
    failure_reasons, report, model.
    """
    client, model = make_llm_client()
    if model_override:
        model = model_override

    project = detect_maven_project(project_path)
    class_name, method_name = parse_target(target)
    class_file = find_class_file(project, class_name)
    if class_file is None:
        return {"status": "error", "report": f"클래스 {class_name!r}를 찾지 못했다"}
    class_source = class_file.read_text(encoding="utf-8")
    package = read_package(class_source)
    test_class = test_class or default_test_class(class_name, method_name)
    test_path = project.test_source_dir.joinpath(*package.split("."), f"{test_class}.java")
    test_rel = test_path.relative_to(project.root).as_posix()

    sandbox = DockerSandbox()
    cache_dir = project.root / CACHE_DIR_NAME
    runner = JavaTestRunner(project, sandbox, cache_dir)

    if not cache_dir.is_dir():
        warmup = warmup_test or find_existing_test_class(project)
        if not warmup:
            return {"status": "error", "report": "준비 단계에 예열할 기존 테스트가 없다"}
        print(f"[준비] 의존성 다운로드 + 예열({warmup}) — 최초 1회, 수 분 걸릴 수 있다...")
        prepared = runner.prepare(warmup)
        if prepared.exit_code != 0:
            return {
                "status": "error",
                "report": f"준비 실패 (exit {prepared.exit_code})\n{prepared.output[-2000:]}",
            }

    config = load_gate_config(project.root)
    baseline = snapshot_baseline(project)  # 게이트 기준선 — 생성 시작 전에 뜬다

    target_lines: set[int] = set()
    if method_name:
        span = next((s for s in method_line_spans(class_source) if s.name == method_name), None)
        if span:
            target_lines = set(range(span.start_line, span.end_line + 1))

    def make_gates():
        gates = [
            AssertIntegrityGate(project, baseline),
            SkipAnnotationGate(project, baseline),
            FileScopeGate(project, baseline, allowed={test_rel}),
        ]
        if fast:
            return gates
        if target_lines:
            gates.append(
                CoverageGate(
                    project,
                    sandbox,
                    cache_dir,
                    test_class,
                    f"{class_name}.java",
                    target_lines,
                    config,
                )
            )
        fq = f"{package}.{{}}" if package else "{}"
        gates.append(
            MutationGate(
                project,
                sandbox,
                cache_dir,
                fq.format(class_name),
                fq.format(test_class),
                config.mutation_min,
                target_method=method_name or None,
            )
        )
        return gates

    instruction = (
        f"{target}에 대한 새 테스트를 만들라. "
        f"테스트 클래스 이름은 {test_class}, 패키지는 {package or '(기본 패키지)'}."
    )
    if instruction_extra:
        instruction += f" 추가 요구: {instruction_extra}"

    ports = WriterPorts(
        inspector=JavaSourceInspector(project),
        graph=ParsingCodeGraph(JavaSimilarTestFinder(project)),
        writer=JavaTestWriter(project, sandbox, cache_dir),
        runner=runner,
        checker=AssertCountChecker(project),
        gate=InterruptUserGate(),
        generator=PromptedGenerator(
            client,
            model,
            "Java",
            "JUnit 5",
            "프로젝트의 기존 테스트 스타일(이름 규칙, import 방식)을 따른다.",
        ),
    )
    app = build_writer_graph(ports, checkpointer=MemorySaver())
    ask = ask_user or (lambda q: UserReply(action="continue"))

    def run_writer(state):
        return invoke_with_interrupts(app, state, thread_id=str(uuid.uuid4()), ask_user=ask)

    def make_state(current_instruction: str):
        return {
            "instruction": current_instruction,
            "target": target,
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
        }

    print(f"[실행] 대상 {target} → {test_rel} (모델: {model})")
    started = time.monotonic()
    result = generate_with_gates(
        run_writer=run_writer,
        make_state=make_state,
        make_gates=make_gates,
        base_instruction=instruction,
        max_retries=config.max_retries,
    )
    elapsed = time.monotonic() - started

    gate_results = [
        (g.name, g.passed, g.reason)
        for g in (result.gate_report.results if result.gate_report else [])
    ]
    # 생성물을 제안으로 옮기고 소스 트리는 원상 복구 — 반영은 apply만 한다(v4 Step 3)
    proposal_name = None
    if Path(test_path).is_file():
        code = Path(test_path).read_text(encoding="utf-8")
        Path(test_path).unlink()
        if result.status in ("accepted", "human_review"):
            status = STATUS_ACCEPTED if result.status == "accepted" else STATUS_NEEDS_REVIEW
            save_proposal(
                project,
                test_class,
                target,
                test_rel,
                code,
                status,
                [
                    f"[{n}] {'통과' if p else '탈락'} — {r.splitlines()[0]}"
                    for n, p, r in gate_results
                ],
            )
            proposal_name = test_class

    return {
        "status": result.status,
        "proposal": proposal_name,
        "attempts": result.attempts,
        "writer_attempts": result.final_state.get("attempts", 0),
        "elapsed": elapsed,
        "test_rel": test_rel,
        "gate_results": gate_results,
        "failure_reasons": result.gate_report.failure_reasons if result.gate_report else "",
        "report": result.final_state.get("report", ""),
        "model": model,
    }
