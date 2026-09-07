"""cta graph — 코드 그래프 빌드 (M4). scripts/build_graph.py를 CLI로 옮긴 것."""

from cta.adapters.java.coverage import JacocoCoverageCollector
from cta.adapters.java.graph_builder import build_graph
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.runner import JavaTestRunner
from cta.cli.generate import CACHE_DIR_NAME, ensure_prepared
from cta.graph.model import NODE_METHOD
from cta.llm.config import load_dotenv_into_env
from cta.sandbox.factory import RUNNER_DOCKER, choose_runner, make_sandbox


def run_graph_build(args) -> int:
    load_dotenv_into_env()
    from cta.graph.neo4j_store import Neo4jGraphStore

    project = detect_maven_project(args.project)
    project_key = str(project.root)

    nodes, edges = build_graph(project)
    print(f"파싱 완료: 노드 {len(nodes)}개, 정적 엣지 {len(edges)}개")

    if args.coverage:
        # 실행 장치는 generate/maintain과 같은 규칙(ADR-0022):
        # 기본 local, --runner docker면 격리 + 준비 단계
        runner_kind = choose_runner(getattr(args, "runner", None), False)
        sandbox = make_sandbox(runner_kind)
        cache_dir = project.root / CACHE_DIR_NAME
        if runner_kind == RUNNER_DOCKER:
            problem = ensure_prepared(
                project, JavaTestRunner(project, sandbox, cache_dir), cache_dir, None
            )
            if problem:
                print(f"오류: {problem}")
                return 1
        test_classes = sorted(p.stem for p in project.test_source_dir.rglob("*Test.java"))
        print(f"[실측] 테스트 클래스 {len(test_classes)}개 커버리지 수집 중...")
        covers = JacocoCoverageCollector(project, sandbox, cache_dir).collect_edges(test_classes)
        edges = edges + covers
        print(f"COVERS 엣지 {len(covers)}개 수집")

    store = Neo4jGraphStore()
    try:
        store.replace_project(project_key, nodes, edges)
    finally:
        store.close()
    methods = sum(1 for n in nodes if n.kind == NODE_METHOD)
    print(f"Neo4j 저장 완료 — project={project_key}")
    print(f"  클래스 {len(nodes) - methods}, 메서드 {methods}, 엣지 {len(edges)}")
    return 0
