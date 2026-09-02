"""Neo4j 저장소 왕복 통합 테스트 — 실제 Neo4j 컨테이너 필요 (marker: neo4j).

기본 pytest 실행에서는 제외된다. 실행 방법:
  docker run -d --name cta-neo4j -e NEO4J_AUTH=neo4j/<암호> -p 7687:7687 -p 7474:7474 neo4j:5
  .env에 CTA_NEO4J_PASSWORD=<암호> 설정 후: pytest -m neo4j
"""

import pytest

from cta.graph.model import EDGE_DECLARES, GraphEdge, GraphNode
from cta.llm.config import load_dotenv_into_env

PROJECT = "cta-test-roundtrip"


@pytest.mark.neo4j
def test_저장_조회_왕복이_인메모리와_같은_계약으로_동작한다():
    load_dotenv_into_env()
    from cta.graph.neo4j_store import Neo4jGraphStore

    store = Neo4jGraphStore()
    try:
        nodes = [
            GraphNode("Class", "Calc", {"is_test": False}),
            GraphNode(
                "Method",
                "Calc#add",
                {
                    "class_name": "Calc",
                    "param_count": 2,
                    "uses_exception": False,
                    "is_test": False,
                    "snippet": "int add(...)",
                },
            ),
            GraphNode(
                "Method",
                "CalcTest#add_test",
                {
                    "class_name": "CalcTest",
                    "param_count": 0,
                    "uses_exception": False,
                    "is_test": True,
                    "snippet": "@Test void ...",
                },
            ),
        ]
        edges = [GraphEdge(EDGE_DECLARES, "Calc", "Calc#add")]
        store.replace_project(PROJECT, nodes, edges)

        declared = store.neighbors(PROJECT, "Calc#add", EDGE_DECLARES, "in")
        assert [n.key for n in declared] == ["Calc"]
        tests = store.methods_by_kind(PROJECT, is_test=True)
        assert [n.key for n in tests] == ["CalcTest#add_test"]
        assert tests[0].props["snippet"] == "@Test void ..."

        # 재빌드(교체)가 이전 데이터를 남기지 않는지
        store.replace_project(PROJECT, nodes[:1], [])
        assert store.methods_by_kind(PROJECT, is_test=True) == []
    finally:
        store.replace_project(PROJECT, [], [])  # 정리
        store.close()
