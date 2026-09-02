"""cta — Code Test Agent CLI 진입점.

설치(pip install -e .) 후 어디서든 `cta <명령>`으로 사용한다. 시나리오수립.md의 기능 이름과
명령의 대응(ADR-0015 D1): 테스트 생성 기능=generate, 변경 대응 기능=maintain,
판단 전달 기능=resolve, 변경 내용 확인 기능=diff, 반영 기능=apply.
핵심 흐름: generate/maintain으로 테스트를 만들면 **제안**으로 보관되고,
diff로 검토 → apply로만 소스 트리에 반영된다(v4 Step 3). 층: cli(조립·입출력만).
"""

import argparse
from pathlib import Path

from cta.cli.locate import resolve_project
from cta.cli.proposals import (
    STATUS_ACCEPTED,
    apply_proposal,
    discard_proposal,
    list_proposals,
    render_diff,
    select_names,
)
from cta.cli.render import EXIT_CODES


def _cmd_generate(args) -> int:
    from cta.cli.generate import DEFAULT_MAX_METHODS, ask_on_terminal, run_generation

    given = [x for x in (args.file, args.class_name, args.target) if x]
    if len(given) != 1:
        print("사용법: cta generate <파일명>  |  --class <클래스>  |  --target 'C#m1,m2'  (하나만)")
        return 1
    if args.file:
        from cta.adapters.java.maven import detect_maven_project
        from cta.cli.file_mode import project_root_for, resolve_file

        root = Path.cwd()
        class_file = resolve_file(root, args.file, args.non_interactive)
        if class_file is None:
            return 1
        project = detect_maven_project(project_root_for(class_file, root))
        if class_file.resolve().is_relative_to(project.test_source_dir.resolve()):
            print(f"{class_file.name}은 테스트 파일이다 — 대상은 main 소스여야 한다")
            return 1
        target = class_file.stem
    else:
        project = resolve_project(args.project, args.non_interactive)
        if project is None:
            return 1
        target = args.class_name or args.target
    outcome = run_generation(
        project_path=str(project.root),
        target=target,
        test_class=args.test_class,
        instruction_extra=args.instruction,
        model_override=args.model,
        warmup_test=args.warmup_test,
        fast=args.fast,
        ask_user=None if args.non_interactive else ask_on_terminal,
        max_methods=args.max_methods if args.max_methods else DEFAULT_MAX_METHODS,
        include_all=args.all,
    )
    if outcome["status"] == "error":
        print(f"오류: {outcome['report']}")
        return 1
    if outcome.get("proposal"):
        print(f"\n다음: cta diff   → 검토      cta apply {outcome['proposal']}   → 반영")
    if outcome["status"] == "human_review":
        print(f"[!] 게이트 탈락 — 사람 확인용 제안으로 저장됨:\n{outcome['failure_reasons']}")
    elif outcome["status"] == "not_passed":
        print(f"\n한계 보고:\n{outcome['report']}")
    return EXIT_CODES[outcome["status_label"]]


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


def _with_project(func):
    """--project 생략을 자동 인식으로 채운 뒤 서브커맨드 함수를 부른다."""

    def run(args):
        project = resolve_project(args.project, getattr(args, "non_interactive", False))
        if project is None:
            return 1
        args.project = str(project.root)
        return func(args)

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cta",
        description="Code Test Agent — 코드 변경에 맞춰 테스트를 생성·유지보수하는 CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser(
        "generate", help="테스트 생성 기능: 클래스의 테스트 없는 메서드에 생성 → 제안 보관"
    )
    g.add_argument(
        "file", nargs="?", help="파일 이름 (예: OrderService.java) — 현재 폴더 하위에서 탐색"
    )
    g.add_argument(
        "--class", dest="class_name", help="대상 클래스 (예: com.example.order.OrderService)"
    )
    g.add_argument("--target", help='특정 메서드만 지정: "클래스#메서드1,메서드2"')
    g.add_argument("--max-methods", type=int, help="테스트 만들 메서드 수 상한 (기본 4)")
    g.add_argument("--project", help="Maven 프로젝트 루트 (생략 시 현재 위치에서 자동 인식)")
    g.add_argument(
        "--all", action="store_true", help="이미 테스트가 참조하는 메서드도 생성 대상에 포함"
    )
    g.add_argument("--test-class", help="테스트 클래스 이름 (기본: <클래스>Test)")
    g.add_argument("--instruction", default="", help="지침에 덧붙일 요구사항")
    g.add_argument("--model", help="이번 실행만 다른 모델")
    g.add_argument("--warmup-test", help="준비 단계 예열용 기존 테스트")
    g.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    g.add_argument("--non-interactive", action="store_true", help="질문 없이 자동 진행")
    g.set_defaults(func=_cmd_generate)

    m = sub.add_parser(
        "maintain", help="변경 대응 기능: git 변경 → 의도 판단(건별 출력) → 규칙표 → 처리"
    )
    m.add_argument(
        "--diff",
        default="HEAD",
        help="비교할 커밋 범위의 기준 (기본 HEAD = 미커밋 변경, 예: HEAD~1)",
    )
    m.add_argument("--project", help="Maven 프로젝트 루트 (생략 시 현재 위치에서 자동 인식)")
    m.add_argument("--plan-only", action="store_true", help="판단만 출력하고 처리하지 않음")
    m.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    m.add_argument("--non-interactive", action="store_true", help="작성 루프의 질문 없이 진행 (CI)")

    def _maintain(args):
        from cta.cli.maintain_cmd import run_maintain

        return run_maintain(args)

    m.set_defaults(func=_with_project(_maintain))

    rs = sub.add_parser("resolve", help="판단 전달 기능: 사람 확인 항목에 답해 멈춘 지점부터 재개")
    rs.add_argument("id", nargs="?", help="사람 확인 항목 id (생략 시 목록, 1건이면 자동 선택)")
    rs.add_argument(
        "--intended",
        action="store_true",
        help="일부러 동작을 바꾼 게 맞다 → 기대값을 새 기준으로 수정",
    )
    rs.add_argument(
        "--test-issue",
        action="store_true",
        help="테스트 쪽 문제다 → 실패 테스트를 동작 기준으로 재작성",
    )
    rs.add_argument("--proceed", action="store_true", help="(질문 항목) 계획대로 테스트 생성")
    rs.add_argument("--skip", action="store_true", help="이번엔 건너뜀 (기록만)")
    rs.add_argument("--hint", default="", help="에이전트에 전달할 지시")
    rs.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    rs.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    rs.add_argument("--non-interactive", action="store_true", help="작성 루프의 질문 없이 진행")

    def _resolve(args):
        from cta.cli.resolve_cmd import run_resolve

        return run_resolve(args)

    rs.set_defaults(func=_with_project(_resolve))

    d = sub.add_parser("diff", help="변경 내용 확인 기능: 대기 중인 제안 목록·내용 검토")
    d.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    d.add_argument("name", nargs="?", help="제안 이름 (생략 시 목록, 1건이면 바로 diff)")
    d.set_defaults(func=_cmd_diff)

    a = sub.add_parser("apply", help="반영 기능: 제안을 테스트 트리에 저장")
    a.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    a.add_argument("name", nargs="?", help="제안 이름 (생략 시 1건이면 자동 선택)")
    a.add_argument("--all", action="store_true", help="대기 중인 제안 전부 반영")
    a.set_defaults(func=_cmd_apply)

    x = sub.add_parser("discard", help="제안 폐기")
    x.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    x.add_argument("name", nargs="?", help="제안 이름 (생략 시 1건이면 자동 선택)")
    x.add_argument("--all", action="store_true", help="전부 폐기")
    x.set_defaults(func=_cmd_discard)

    gr = sub.add_parser("graph", help="프로젝트 분석 기능: 코드 그래프 빌드 (Neo4j)")
    gr.add_argument("--project", help="생략 시 현재 위치에서 자동 인식")
    gr.add_argument("--coverage", action="store_true", help="JaCoCo 실측 COVERS까지 수집")

    def _graph(args):
        from cta.cli.graph_cmd import run_graph_build

        return run_graph_build(args)

    gr.set_defaults(func=_with_project(_graph))

    e = sub.add_parser("eval", help="결함 세트로 검출률 실측 (개발용)")
    e.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    e.add_argument("--cases", help="쉼표로 구분한 케이스 id (기본: 전체)")

    def _eval(args):
        from cta.cli.eval_cmd import run_eval

        return run_eval(args)

    e.set_defaults(func=_eval)

    dm = sub.add_parser("demo", help="대표 시나리오 재생 시연 (LLM 비용 0)")

    def _demo(args):
        from cta.cli.demo_cmd import run_demo

        return run_demo(args)

    dm.set_defaults(func=_demo)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
