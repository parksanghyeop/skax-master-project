"""코드 그래프 빌드 CLI — Maven 프로젝트를 파싱해 Neo4j에 넣는다 (M4).

사용 예:
  .venv/Scripts/python scripts/build_graph.py --project examples/demo
  .venv/Scripts/python scripts/build_graph.py --project examples/demo --coverage

--coverage: 테스트 클래스별로 JaCoCo 실측을 돌려 COVERS(검증한다) 엣지까지
만든다(Docker + 준비된 의존성 캐시 필요, 테스트 수에 비례해 오래 걸린다).
Neo4j 접속은 .env의 CTA_NEO4J_URI/USER/PASSWORD (v4 6.5: 샌드박스 밖 별도 컨테이너).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from adapters.java.coverage import JacocoCoverageCollector  # noqa: E402
from adapters.java.graph_builder import build_graph  # noqa: E402
from adapters.java.maven import detect_maven_project, find_existing_test_class  # noqa: E402
from adapters.java.runner import JavaTestRunner  # noqa: E402
from graph.model import NODE_METHOD  # noqa: E402
from llm.config import load_dotenv_into_env  # noqa: E402
from sandbox.docker_sandbox import DockerSandbox  # noqa: E402

CACHE_DIR_NAME = ".cta/m2repo"  # generate_test.py와 같은 캐시를 공유한다


def main() -> int:
    parser = argparse.ArgumentParser(description="Maven 프로젝트의 코드 그래프를 빌드한다")
    parser.add_argument("--project", required=True, help="Maven 프로젝트 루트 (pom.xml 위치)")
    parser.add_argument(
        "--coverage", action="store_true", help="JaCoCo 실측으로 COVERS 엣지까지 수집 (Docker 필요)"
    )
    args = parser.parse_args()

    load_dotenv_into_env()
    from graph.neo4j_store import Neo4jGraphStore

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


if __name__ == "__main__":
    raise SystemExit(main())
