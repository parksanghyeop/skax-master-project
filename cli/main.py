"""cta — Code Test Agent CLI 진입점.

설치(pip install -e .) 후 어디서든 `cta <명령>`으로 사용한다.
핵심 흐름: generate/run으로 테스트를 만들면 **제안**으로 보관되고,
diff로 검토 → apply로만 소스 트리에 반영된다(v4 Step 3).
"""

import argparse

from cli.locate import resolve_project
from cli.proposals import (
    STATUS_ACCEPTED,
    apply_proposal,
    discard_proposal,
    list_proposals,
    render_diff,
    select_names,
)


def _cmd_generate(args) -> int:
    # 파일 모드: `cta generate Calculator.java` — 탐색·계획 후 메서드별 생성
    if args.file:
        if args.target:
            print("파일 이름과 --target은 함께 쓸 수 없다 — 하나만 지정하라")
            return 1
        from cli.file_mode import run_file_mode

        return run_file_mode(args)
    if not args.target:
        print("사용법: cta generate <파일명>  또는  cta generate --target 'C#m'")
        return 1
    project = resolve_project(args.project, args.non_interactive)
    if project is None:
        return 1
    from cli.generate import ask_on_terminal, run_generation

    outcome = run_generation(
        project_path=str(project.root),
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
        print(f"\n제안 저장됨: {outcome['proposal']}  (반영 위치: {outcome['test_rel']})")
        print("다음: cta diff   → 검토")
        print(f"      cta apply {outcome['proposal']}   → 반영")
        return 0
    if outcome["status"] == "human_review":
        print("\n[!] 게이트 탈락 — 사람 확인용 제안으로 저장됨:")
        print(outcome["failure_reasons"])
        print(f"검토: cta diff {outcome['proposal']}")
        return 3
    print(f"\n한계 보고:\n{outcome['report']}")
    return 2


def _cmd_diff(args) -> int:
    project = resolve_project(args.project)
    if project is None:
        return 1
    proposals = list_proposals(project)
    if not proposals:
        print("대기 중인 제안 없음")
        return 0
    if args.name:
        print(render_diff(project, args.name))
        return 0
    # 제안이 1건이면 목록 대신 바로 diff까지 보여준다 — 한 단계 덜 치게
    if len(proposals) == 1:
        p = proposals[0]
        mark = "게이트 통과" if p.status == STATUS_ACCEPTED else "사람 확인 필요"
        print(f"■ {p.name}  [{mark}]  대상 {p.target}  ({p.created_at})\n")
        print(render_diff(project, p.name))
        return 0
    print(f"대기 중인 제안 {len(proposals)}건:")
    for p in proposals:
        mark = "게이트 통과" if p.status == STATUS_ACCEPTED else "사람 확인 필요"
        print(f"\n■ {p.name}  [{mark}]  대상 {p.target}  ({p.created_at})")
        for line in p.gate_summary:
            print(f"    {line}")
        print(f"    상세 diff: cta diff {p.name}")
    return 0


def _cmd_apply(args) -> int:
    project = resolve_project(args.project)
    if project is None:
        return 1
    names = select_names(project, args.name, args.all)
    if names is None:
        return 1
    for name in names:
        dest = apply_proposal(project, name)
        print(f"반영됨: {name} → {dest.relative_to(project.root)}")
    print("커밋 전에 테스트를 한 번 돌려 확인하는 것을 권장한다.")
    return 0


def _cmd_discard(args) -> int:
    project = resolve_project(args.project)
    if project is None:
        return 1
    names = select_names(project, args.name, args.all)
    if names is None:
        return 1
    for name in names:
        discard_proposal(project, name)
        print(f"폐기됨: {name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cta",
        description="Code Test Agent — 코드 변경에 맞춰 테스트를 생성·유지보수하는 CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="파일/메서드에 테스트 생성 → 제안으로 보관")
    g.add_argument(
        "file",
        nargs="?",
        help="파일 이름 하나로 간편 실행 (예: Calculator.java) — 현재 폴더 하위에서 탐색",
    )
    g.add_argument("--project", help="Maven 프로젝트 루트 (생략 시 현재 위치에서 자동 인식)")
    g.add_argument("--target", help='특정 메서드만 지정: "클래스#메서드"')
    g.add_argument(
        "--all", action="store_true", help="파일 모드: 이미 테스트가 참조하는 메서드도 생성"
    )
    g.add_argument("--test-class", help="테스트 클래스 이름 (기본: <클래스><메서드>Test)")
    g.add_argument("--instruction", default="", help="지침에 덧붙일 요구사항")
    g.add_argument("--model", help="이번 실행만 다른 모델")
    g.add_argument("--warmup-test", help="준비 단계 예열용 기존 테스트")
    g.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    g.add_argument("--non-interactive", action="store_true", help="질문 없이 자동 진행")
    g.set_defaults(func=_cmd_generate)

    r = sub.add_parser("run", help="git 변경에서 자동 판단 → (필요 시) 테스트 생성")
    r.add_argument("--project", help="Maven 프로젝트 루트 (생략 시 현재 위치에서 자동 인식)")
    r.add_argument("--base", default="HEAD", help="diff 기준 (기본: 미커밋 변경)")
    r.add_argument("--message", default="", help="커밋 메시지 등 의도 단서")
    r.add_argument(
        "--intent",
        choices=["bug_fix", "refactor", "new_feature"],
        help="의도를 확실히 알면 직접 지정 — LLM 분류 생략",
    )
    r.add_argument("--execute", action="store_true", help="생성까지 실행 (기본: 결정만 출력)")
    r.add_argument("--non-interactive", action="store_true", help="사람 확인을 묻지 않음 (CI)")

    def _run(args):
        project = resolve_project(args.project, args.non_interactive)
        if project is None:
            return 1
        args.project = str(project.root)
        from cli.pipeline_cmd import run_pipeline

        return run_pipeline(args)

    r.set_defaults(func=_run)

    d = sub.add_parser("diff", help="대기 중인 제안 목록·내용 검토")
    d.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    d.add_argument("name", nargs="?", help="제안 이름 (생략 시 목록, 1건이면 바로 diff)")
    d.set_defaults(func=_cmd_diff)

    a = sub.add_parser("apply", help="제안을 테스트 트리에 반영")
    a.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    a.add_argument("name", nargs="?", help="제안 이름 (생략 시 1건이면 자동 선택)")
    a.add_argument("--all", action="store_true", help="대기 중인 제안 전부 반영")
    a.set_defaults(func=_cmd_apply)

    x = sub.add_parser("discard", help="제안 폐기")
    x.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    x.add_argument("name", nargs="?", help="제안 이름 (생략 시 1건이면 자동 선택)")
    x.add_argument("--all", action="store_true", help="전부 폐기")
    x.set_defaults(func=_cmd_discard)

    gr = sub.add_parser("graph", help="코드 그래프 빌드 (Neo4j)")
    gr.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    gr.add_argument("--coverage", action="store_true", help="JaCoCo 실측 COVERS까지 수집")

    def _graph(args):
        project = resolve_project(args.project)
        if project is None:
            return 1
        args.project = str(project.root)
        from cli.graph_cmd import run_graph_build

        return run_graph_build(args)

    gr.set_defaults(func=_graph)

    e = sub.add_parser("eval", help="결함 세트로 검출률 실측 (개발용)")
    e.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    e.add_argument("--cases", help="쉼표로 구분한 케이스 id (기본: 전체)")

    def _eval(args):
        from cli.eval_cmd import run_eval

        return run_eval(args)

    e.set_defaults(func=_eval)

    dm = sub.add_parser("demo", help="대표 시나리오 재생 시연 (LLM 비용 0)")

    def _demo(args):
        from cli.demo_cmd import run_demo

        return run_demo(args)

    dm.set_defaults(func=_demo)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
