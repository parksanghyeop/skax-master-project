"""cta graph — 코드 그래프 빌드 (M4). scripts/build_graph.py를 CLI로 옮긴 것."""

from cta.adapters.java.coverage import JacocoCoverageCollector
from cta.adapters.java.graph_builder import build_graph
from cta.adapters.java.maven import detect_maven_project, find_existing_test_class
from cta.adapters.java.runner import JavaTestRunner
from cta.cli.generate import CACHE_DIR_NAME
from cta.graph.model import NODE_METHOD
from cta.llm.config import load_dotenv_into_env
from cta.sandbox.docker_sandbox import DockerSandbox


def run_graph_build(args) -> int:
    load_dotenv_into_env()
    from cta.graph.neo4j_store import Neo4jGraphStore

    project = detect_maven_project(args.project)
    project_key = str(project.root)

    nodes, edges = build_graph(project)
    print(f"파싱 완료: 노드 {len(nodes)}개, 정적 엣지 {len(edges)}개")

    if args.coverage:
        sandbox = DockerSandbox()
        cache_dir = project.root / CACHE_DIR_NAME
        if not cache_dir.is_dir():
            warmup = find_existing_test_class(project)
            if not warmup:
                print("오류: 준비 단계에 예열할 기존 테스트가 없다")
                return 1
            print(f"[준비] 의존성 캐시 생성 + 예열({warmup}) — 최초 1회...")
            prepared = JavaTestRunner(project, sandbox, cache_dir).prepare(warmup)
            if prepared.exit_code != 0:
                print(f"오류: 준비 실패\n{prepared.output[-1500:]}")
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
