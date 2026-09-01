"""cta run — 변경 추출 → 의도 분류 → 조치 결정 → (선택) 생성 (v4 2.1 파이프라인).

escalate/ask 결정은 터미널에서 사람의 답을 받아 이어간다. create_test 실행은
cta generate와 같은 경로라 결과는 '제안'으로 보관된다. 층: cli(조립).
"""

from adapters.java.changes import GitChangeExtractor
from adapters.java.maven import detect_maven_project
from adapters.java.runner import JavaTestRunner
from cli.generate import CACHE_DIR_NAME, ask_on_terminal, run_generation
from core.pipeline.decide import decide
from core.pipeline.models import (
    ACTION_ASK,
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    Intent,
)
from graph.model import EDGE_COVERS
from llm.config import load_dotenv_into_env, make_llm_client
from llm.intent import PromptedIntentClassifier
from sandbox.docker_sandbox import DockerSandbox


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


def run_pipeline(args) -> int:
    load_dotenv_into_env()
    project = detect_maven_project(args.project)
    project_key = str(project.root)

    # 1단계: 변경 추출 (일반 코드)
    changes = GitChangeExtractor(project, args.base).extract()
    if not changes:
        print("변경 없음 — 할 일이 없다")
        return 0
    print(f"[변경 추출] {len(changes)}개 심볼: {', '.join(c.target for c in changes)}")

    # 2단계: 의도 분류 — 작성자 지정이면 LLM 생략, 아니면 LLM 1회
    if args.intent:
        intent = Intent(
            category=args.intent,
            analysis=f"작성자 지정 의도({args.intent}). 메시지: {args.message or '(없음)'}",
        )
        print(f"[의도 분류] {intent.category} (작성자 지정 — LLM 호출 생략)")
    else:
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

    # 4단계: escalate/ask 해소 — 사람이 답해야 재개된다
    resolved = []
    for decision in decisions:
        if decision.kind not in (ACTION_ESCALATE, ACTION_ASK):
            resolved.append(decision)
            continue
        print(f"\n[일시정지] 사람 확인 필요 [{decision.kind}] {decision.target}")
        print(f"   사유: {decision.reason}")
        print(f"   지침서:\n{decision.briefing}")
        if args.non_interactive:
            print("   (--non-interactive: 보고만 하고 건너뜀)")
            continue
        raw = (
            input("   답 [c=테스트 생성으로 진행 / Enter=건너뛰기 / 그 외=힌트와 함께 진행]: ")
            .lstrip("﻿")
            .strip()
        )
        if not raw:
            print("   → 건너뜀 (기록됨)")
            continue
        briefing = (
            decision.briefing if raw.lower() == "c" else f"{decision.briefing}\n사람의 지시: {raw}"
        )
        resolved.append(
            type(decision)(
                kind=ACTION_CREATE_TEST,
                target=decision.target,
                briefing=briefing,
                reason=f"{decision.reason} → 사람이 진행 결정",
            )
        )
        print("   → 사람 결정으로 재개: 테스트 생성 진행")
    decisions = resolved

    # 5단계: 실행 (선택) — create_test만, 결과는 제안으로 보관
    for decision in decisions:
        if decision.kind != ACTION_CREATE_TEST:
            continue
        if not args.execute:
            print(f"\n(계획만 출력) {decision.target}에 테스트 생성 예정 — --execute로 실행")
            continue
        print(f"\n[실행] {decision.target}에 테스트 생성...")
        outcome = run_generation(
            project_path=str(project.root),
            target=decision.target,
            instruction_extra=decision.briefing.replace("\n", " "),
            ask_user=None if args.non_interactive else ask_on_terminal,
        )
        if outcome.get("proposal"):
            print(
                f"[결과] {outcome['status']} → 제안 {outcome['proposal']!r} 저장됨 "
                f"(cta diff / cta apply로 검토·반영)"
            )
        else:
            print(f"[결과] {outcome['status']}: {outcome.get('report', '')[:300]}")
    return 0
