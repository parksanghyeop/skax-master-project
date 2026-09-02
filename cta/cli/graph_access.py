"""코드 그래프 접속 — Neo4j가 있으면 실물, 없으면 파싱 폴백을 고르는 공통 입구.

generate(유사 테스트 검색)와 maintain(검증 테스트 찾기)이 같은 규칙으로 그래프를 쓴다.
드라이버 생성은 접속 없이 성공하므로, 가벼운 질의로 접속을 확인한 뒤에야 "있다"고 본다
(hardening-notes 2026-09-03: 폴백이 질의 시점에 터진 문제). 층: cli.
"""

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph
from cta.core.ports import CodeGraph
from cta.graph.answers import GraphCodeGraph
from cta.graph.model import EDGE_COVERS

GRAPH_NOTE = "코드 그래프(Neo4j 실측)"
FALLBACK_NOTE = "소스 파싱 폴백 (그래프 미접속 — cta graph --coverage로 정확도 향상)"


def try_open_store(project_key: str):
    """접속 가능한 Neo4jGraphStore를 돌려준다. 설정 없음·서버 미가동이면 None(폴백 신호)."""
    try:
        from cta.graph.neo4j_store import Neo4jGraphStore

        store = Neo4jGraphStore()
        store.neighbors(project_key, "__probe__", EDGE_COVERS, "in")  # 접속 확인용 질의
        return store
    except Exception:
        return None


def choose_code_graph(project: MavenProject) -> tuple[CodeGraph, str, object | None]:
    """(CodeGraph 구현, 화면 안내 문구, 닫아야 할 저장소 또는 None)."""
    key = str(project.root)
    store = try_open_store(key)
    if store is None:
        return ParsingCodeGraph(JavaSimilarTestFinder(project)), FALLBACK_NOTE, None
    return GraphCodeGraph(store, key), GRAPH_NOTE, store
