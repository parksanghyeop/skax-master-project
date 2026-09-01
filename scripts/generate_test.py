"""테스트 생성 CLI (PoC 최소본) — 지정한 Maven 프로젝트의 메서드에 새 테스트를 만든다.

사용 예:
  .venv/Scripts/python scripts/generate_test.py --project examples/demo --target Calculator#divide

동작: 대상 조사 → 비슷한 기존 테스트 수집 → LLM(사내 게이트웨이) 생성 →
인터넷 차단 Docker 환경에서 컴파일·실행 → 품질 검사. 통과하면 테스트 파일이
프로젝트에 남는다(적용 여부는 사람이 diff로 확인 후 결정).
정식 CLI(전체 명령·설정)는 3단계 범위 — 이 스크립트는 실사용 검증용 진입점이다.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from adapters.fake import ScriptedUserGate  # noqa: E402
from adapters.java.inspector import JavaSourceInspector  # noqa: E402
from adapters.java.maven import detect_maven_project, find_existing_test_class  # noqa: E402
from adapters.java.parsing import find_class_file, parse_target, read_package  # noqa: E402
from adapters.java.quality import AssertCountChecker  # noqa: E402
from adapters.java.runner import JavaTestRunner  # noqa: E402
from adapters.java.similar import JavaSimilarTestFinder  # noqa: E402
from adapters.java.writer import JavaTestWriter  # noqa: E402
from core.writer_graph import WriterPorts, build_writer_graph  # noqa: E402
from llm.config import make_llm_client  # noqa: E402
from llm.generation import PromptedGenerator  # noqa: E402
from sandbox.docker_sandbox import DockerSandbox  # noqa: E402

# 준비 단계에서 만드는 의존성 캐시 위치 — 대상 프로젝트 밑에 두어 지우기 쉽게 한다.
CACHE_DIR_NAME = ".cta/m2repo"


def default_test_class(class_name: str, method_name: str) -> str:
    """--test-class 생략 시 이름 규칙: Calculator#divide → CalculatorDivideTest."""
    suffix = method_name[:1].upper() + method_name[1:] if method_name else "Generated"
    return f"{class_name}{suffix}Test"


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
    args = parser.parse_args()

    client, model = make_llm_client()
    if args.model:
        model = args.model

    project = detect_maven_project(args.project)
    class_name, method_name = parse_target(args.target)
    class_file = find_class_file(project, class_name)
    if class_file is None:
        print(f"오류: 클래스 {class_name!r}를 {project.root}에서 찾지 못했다")
        return 1
    package = read_package(class_file.read_text(encoding="utf-8"))
    test_class = args.test_class or default_test_class(class_name, method_name)
    test_path = project.test_source_dir.joinpath(*package.split("."), f"{test_class}.java")

    sandbox = DockerSandbox()
    cache_dir = project.root / CACHE_DIR_NAME
    runner = JavaTestRunner(project, sandbox, cache_dir)

    # 흐름: 캐시 없으면 준비(의존성 다운로드+예열) → 그래프 실행 → 결과 보고
    if not cache_dir.is_dir():
        warmup = args.warmup_test or find_existing_test_class(project)
        if not warmup:
            print("오류: 준비 단계에 예열할 기존 테스트가 없다 — --warmup-test로 지정하라")
            return 1
        print(f"[준비] 의존성 다운로드 + 예열({warmup}) — 최초 1회, 수 분 걸릴 수 있다...")
        prepared = runner.prepare(warmup)
        if prepared.exit_code != 0:
            print(f"오류: 준비 실패 (exit {prepared.exit_code})\n{prepared.output[-2000:]}")
            return 1

    instruction = (
        f"{args.target}에 대한 새 테스트를 만들라. "
        f"테스트 클래스 이름은 {test_class}, 패키지는 {package or '(기본 패키지)'}."
    )
    if args.instruction:
        instruction += f" 추가 요구: {args.instruction}"

    ports = WriterPorts(
        inspector=JavaSourceInspector(project),
        finder=JavaSimilarTestFinder(project),
        writer=JavaTestWriter(project, sandbox, cache_dir),
        runner=runner,
        checker=AssertCountChecker(project),
        gate=ScriptedUserGate(),  # PoC: 질문 지점은 자동 '계속' — 실사용 연결은 2단계
        generator=PromptedGenerator(
            client,
            model,
            "Java",
            "JUnit 5",
            "프로젝트의 기존 테스트 스타일(이름 규칙, import 방식)을 따른다.",
        ),
    )
    print(f"[실행] 대상 {args.target} → {test_path.relative_to(project.root)} (모델: {model})")
    started = time.monotonic()
    final = build_writer_graph(ports).invoke(
        {
            "instruction": instruction,
            "target": args.target,
            "test_path": str(test_path),
            "selector": test_class,
            "context": "",
            "test_code": "",
            "write_result": "",
            "last_run": "",
            "attempts": 0,
            "quality": "",
            "report": "",
            "status": "working",
        }
    )
    elapsed = time.monotonic() - started

    print(f"\n결과: {final['status']}  (시도 {final['attempts']}회, {elapsed:.0f}초)")
    print(f"실행: {final['last_run'].splitlines()[0] if final['last_run'] else '(없음)'}")
    print(f"품질: {final['quality'] or '(검사 전 종료)'}")
    if final["status"] == "passed":
        print(f"\n생성 파일: {test_path}")
        print("내용을 git diff 등으로 검토한 뒤 커밋 여부를 결정하라.")
        return 0
    print(f"\n한계 보고:\n{final['report']}")
    print(f"(생성 시도 파일이 남아 있다면 검토 후 삭제하라: {test_path})")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
