"""테스트 생성 CLI — 지정한 Maven 프로젝트의 메서드에 새 테스트를 만든다 (M6 게이트 연결판).

사용 예:
  .venv/Scripts/python scripts/generate_test.py --project examples/demo --target Calculator#divide

동작: 대상 조사 → 비슷한 기존 테스트 수집 → LLM(사내 게이트웨이) 생성 →
인터넷 차단 Docker 환경에서 컴파일·실행 → **품질 게이트 5종**(assert 훼손·스킵·
파일 범위·커버리지·뮤테이션) 검사. 탈락하면 사유를 모델에게 돌려주고 재시도
(기본 3회), 소진하면 사람 확인 목록으로 보고한다. 반복 중 판단이 필요한 실패는
그 자리에서 멈추고 터미널로 묻는다(계속/중지/힌트).
"""

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from adapters.java.gates import (  # noqa: E402
    AssertIntegrityGate,
    CoverageGate,
    FileScopeGate,
    SkipAnnotationGate,
    snapshot_baseline,
)
from adapters.java.inspector import JavaSourceInspector  # noqa: E402
from adapters.java.maven import detect_maven_project, find_existing_test_class  # noqa: E402
from adapters.java.mutation import MutationGate  # noqa: E402
from adapters.java.parsing import (  # noqa: E402
    find_class_file,
    method_line_spans,
    parse_target,
    read_package,
)
from adapters.java.quality import AssertCountChecker  # noqa: E402
from adapters.java.runner import JavaTestRunner  # noqa: E402
from adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph  # noqa: E402
from adapters.java.writer import JavaTestWriter  # noqa: E402
from core.gates import load_gate_config  # noqa: E402
from core.ports import UserReply  # noqa: E402
from core.submit import generate_with_gates  # noqa: E402
from core.writer_graph import (  # noqa: E402
    InterruptUserGate,
    WriterPorts,
    build_writer_graph,
    invoke_with_interrupts,
)
from llm.config import make_llm_client  # noqa: E402
from llm.generation import PromptedGenerator  # noqa: E402
from sandbox.docker_sandbox import DockerSandbox  # noqa: E402

# 준비 단계에서 만드는 의존성 캐시 위치 — 대상 프로젝트 밑에 두어 지우기 쉽게 한다.
CACHE_DIR_NAME = ".cta/m2repo"


def default_test_class(class_name: str, method_name: str) -> str:
    """--test-class 생략 시 이름 규칙: Calculator#divide → CalculatorDivideTest."""
    suffix = method_name[:1].upper() + method_name[1:] if method_name else "Generated"
    return f"{class_name}{suffix}Test"


def ask_on_terminal(question: str) -> UserReply:
    """반복 중 멈춤 지점의 터미널 응답기 — 계속/중지/힌트를 stdin으로 받는다."""
    print(f"\n⏸ 에이전트가 묻습니다:\n{question}")
    raw = input("답 [Enter=계속 / s=중지 / 그 외 입력=힌트로 전달하고 계속]: ").strip()
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
    """테스트 생성 전체 흐름(준비→기준선→생성→게이트 루프)을 수행한다.

    CLI(main)와 평가 하네스(run_eval)가 공유하는 진입점.
    출력: {"status", "attempts", "writer_attempts", "elapsed", "test_path",
           "gate_results", "failure_reasons", "report"} — status는 SubmitResult의
    상태값 또는 "error"(입력·환경 문제, reason은 report에).
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

    # 흐름: 캐시 준비 → 기준선 스냅샷 → [생성 → 게이트] 루프 → 보고
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

    # 커버리지 판정 대상: 대상 메서드의 줄 범위 (메서드 미지정 시 게이트 생략)
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
        gate=InterruptUserGate(),  # M6 실연결: 멈춤 지점에서 그래프가 정지한다
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
    return {
        "status": result.status,
        "attempts": result.attempts,
        "writer_attempts": result.final_state.get("attempts", 0),
        "elapsed": elapsed,
        "test_path": str(test_path),
        "gate_results": [
            (g.name, g.passed, g.reason)
            for g in (result.gate_report.results if result.gate_report else [])
        ],
        "failure_reasons": result.gate_report.failure_reasons if result.gate_report else "",
        "report": result.final_state.get("report", ""),
        "model": model,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Maven 프로젝트의 메서드에 새 테스트를 생성한다")
    parser.add_argument("--project", required=True, help="Maven 프로젝트 루트 (pom.xml 위치)")
    parser.add_argument(
        "--target", required=True, help='대상 "클래스#메서드" (예: Calculator#divide)'
    )
    parser.add_argument(
        "--test-class", help="생성할 테스트 클래스 이름 (기본: <클래스><메서드>Test)"
    )
    parser.add_argument("--instruction", default="", help="작업 지침에 덧붙일 요구사항")
    parser.add_argument("--model", help="게이트웨이 deployment 이름 (기본: .env의 CTA_LLM_MODEL)")
    parser.add_argument("--warmup-test", help="준비 단계 예열에 쓸 기존 테스트 (기본: 자동 탐지)")
    parser.add_argument(
        "--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략 (결정적 게이트 3종만)"
    )
    parser.add_argument(
        "--non-interactive", action="store_true", help="멈춤 지점에서 묻지 않고 자동 '계속'"
    )
    args = parser.parse_args()

    outcome = run_generation(
        project_path=args.project,
        target=args.target,
        test_class=args.test_class,
        instruction_extra=args.instruction,
        model_override=args.model,
        warmup_test=args.warmup_test,
        fast=args.fast,
        ask_user=None if args.non_interactive else ask_on_terminal,
    )

    if outcome["status"] == "error":
        print(f"오류: {outcome['report']}")
        return 1
    print(
        f"\n결과: {outcome['status']}  "
        f"(게이트 루프 {outcome['attempts']}회, {outcome['elapsed']:.0f}초)"
    )
    for name, passed, reason in outcome["gate_results"]:
        print(f"  게이트[{name}] {'통과' if passed else '탈락'} — {reason.splitlines()[0]}")
    if outcome["status"] == "accepted":
        print(f"\n생성 파일: {outcome['test_path']}")
        print("모든 게이트 통과. 내용을 git diff 등으로 검토한 뒤 커밋 여부를 결정하라.")
        return 0
    if outcome["status"] == "human_review":
        print("\n⚠️ 사람 확인 필요 — 게이트 탈락 사유:")
        print(outcome["failure_reasons"])
        print(f"(검토용으로 파일은 남겨 둠: {outcome['test_path']})")
        return 3
    print(f"\n한계 보고:\n{outcome['report']}")
    print(f"(생성 시도 파일이 남아 있다면 검토 후 삭제하라: {outcome['test_path']})")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
