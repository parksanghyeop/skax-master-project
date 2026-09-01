"""파이프라인 CLI (M5) — 변경 추출 → 의도 분류 → 조치 결정 → (선택) 테스트 생성.

사용 예:
  .venv/Scripts/python scripts/run_pipeline.py --project examples/demo --message "버그 수정"
  .venv/Scripts/python scripts/run_pipeline.py --project examples/demo --execute

기본은 결정까지만 출력(dry-run). --execute면 create_test 결정을 실제로 수행한다.
escalate/ask 결정은 출력으로 보고한다 — 대화형 개입(interrupt)은 M6에서 연결.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from adapters.java.changes import GitChangeExtractor  # noqa: E402
from adapters.java.maven import detect_maven_project  # noqa: E402
from adapters.java.runner import JavaTestRunner  # noqa: E402
from core.pipeline.decide import decide  # noqa: E402
from core.pipeline.models import (  # noqa: E402
    ACTION_CREATE_TEST,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
)
from graph.model import EDGE_COVERS  # noqa: E402
from llm.config import load_dotenv_into_env, make_llm_client  # noqa: E402
from llm.intent import PromptedIntentClassifier  # noqa: E402
from sandbox.docker_sandbox import DockerSandbox  # noqa: E402

CACHE_DIR_NAME = ".cta/m2repo"


def covering_tests(project_key: str, target: str) -> list[str] | None:
    """그래프의 실측 COVERS에서 대상을 커버하는 테스트 클래스를 찾는다.

    그래프가 없거나 접속이 안 되면 None(모름) — 호출부가 폴백을 정한다.
    """
    try:
        from graph.neo4j_store import Neo4jGraphStore

        store = Neo4jGraphStore()
    except Exception:
        return None
    try:
        tests = store.neighbors(project_key, target, EDGE_COVERS, "in")
        return sorted({t.key for t in tests})
    except Exception:
        return None
    finally:
        store.close()


def tests_status(runner: JavaTestRunner, test_classes: list[str] | None) -> str:
    """커버 테스트를 실행해 상태(pass/fail/none)를 얻는다 — 조치 결정의 입력."""
    if not test_classes:
        return TESTS_NONE
    result = runner.run(",".join(test_classes))
    return TESTS_PASS if result.passed else TESTS_FAIL


def main() -> int:
    parser = argparse.ArgumentParser(description="변경 추출→의도 분류→조치 결정 파이프라인")
    parser.add_argument("--project", required=True, help="Maven 프로젝트 루트 (git 저장소)")
    parser.add_argument("--base", default="HEAD", help="diff 기준 (기본 HEAD: 미커밋 변경)")
    parser.add_argument("--message", default="", help="커밋 메시지 등 의도 단서")
    parser.add_argument(
        "--execute", action="store_true", help="create_test 결정을 실제로 수행 (기본: 결정만 출력)"
    )
    args = parser.parse_args()

    load_dotenv_into_env()
    project = detect_maven_project(args.project)
    project_key = str(project.root)

    # 1단계: 변경 추출 (일반 코드)
    changes = GitChangeExtractor(project, args.base).extract()
    if not changes:
        print("변경 없음 — 할 일이 없다")
        return 0
    print(f"[변경 추출] {len(changes)}개 심볼: {', '.join(c.target for c in changes)}")

    # 2단계: 의도 분류 (LLM 1회 — 변경 묶음 전체에 대해 대분류+구체 분석)
    client, model = make_llm_client()
    summary_parts = [f"커밋 메시지: {args.message or '(없음)'}"]
    for c in changes:
        summary_parts.append(
            f"\n### {c.target} (+{c.lines_added}/-{c.lines_removed}"
            f"{', 시그니처 변경' if c.signature_changed else ''})\n{c.diff_excerpt}"
        )
    intent = PromptedIntentClassifier(client, model).classify("\n".join(summary_parts))
    print(f"[의도 분류] {intent.category} — {intent.analysis}")

    # 3단계: 조치 결정 (규칙표 — LLM 없음)
    sandbox = DockerSandbox()
    runner = JavaTestRunner(project, sandbox, project.root / CACHE_DIR_NAME)
    decisions = []
    for change in changes:
        covered_by = covering_tests(project_key, change.target)
        if covered_by is None:
            print(f"  (그래프 미접속 — {change.target}의 커버 테스트를 모름 → 없음으로 간주)")
            covered_by = []
        status = tests_status(runner, covered_by)
        decision = decide(change, intent, status)
        decisions.append(decision)
        print(
            f"[조치 결정] {change.target}: {decision.kind}  ← {decision.reason} "
            f"(기존 테스트: {status})"
        )

    # 4단계: 실행 (선택) — create_test만 자동, escalate/ask는 사람 몫
    for decision in decisions:
        if decision.kind != ACTION_CREATE_TEST:
            continue
        if not args.execute:
            print(
                f"\n(dry-run) {decision.target}에 테스트 생성 예정 — 지침서:\n{decision.briefing}"
            )
            continue
        print(f"\n[실행] {decision.target}에 테스트 생성...")
        import subprocess as sp

        # 왜 하위 프로세스인가: generate_test.py의 준비·경로 계산·보고를 그대로 재사용
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "generate_test.py"),
            "--project",
            str(project.root),
            "--target",
            decision.target,
            "--instruction",
            decision.briefing.replace("\n", " "),
        ]
        code = sp.call(cmd)
        print(f"[실행 결과] 종료 코드 {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
