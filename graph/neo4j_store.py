"""Neo4j 그래프 저장소 — GraphStore의 실물 구현 (v4 6.5).

Neo4j는 Docker 샌드박스 밖의 별도 컨테이너로 구동한다(v4 6.5 — 격리 경계 훼손 금지).
접속 정보는 환경변수/.env로만 받는다(v4 6.6). 동적 라벨·관계 타입 대신
단일 라벨(CodeNode)·단일 관계(REL)에 kind 속성을 쓴다 — Cypher 문자열 조립
(주입 위험·캐시 미스)을 피하는 선택.
"""

import os

from graph.model import GraphEdge, GraphNode

ENV_URI = "CTA_NEO4J_URI"  # 기본 bolt://localhost:7687
ENV_USER = "CTA_NEO4J_USER"  # 기본 neo4j
ENV_PASSWORD = "CTA_NEO4J_PASSWORD"  # 기본 없음(필수)

DEFAULT_URI = "bolt://localhost:7687"
DEFAULT_USER = "neo4j"


class Neo4jConfigError(RuntimeError):
    """접속 정보가 없을 때 — 어떤 환경변수를 채워야 하는지 메시지에 담는다."""


class Neo4jGraphStore:
    """Neo4j 세션 위에서 GraphStore 계약을 구현한다.

    실패 시 동작: 접속 정보 없음 → Neo4jConfigError(생성 시점).
      서버 미가동·인증 실패는 neo4j 드라이버 예외가 그대로 올라온다 —
      환경 문제를 숨기지 않는다.
    """

    def __init__(self) -> None:
        import neo4j  # 지연 import — 인메모리만 쓰는 환경에서 드라이버를 요구하지 않기 위해

        password = os.environ.get(ENV_PASSWORD)
        if not password:
            raise Neo4jConfigError(
                f"환경변수 {ENV_PASSWORD}가 필요하다 (.env 또는 환경변수). "
                f"{ENV_URI}(기본 {DEFAULT_URI})·{ENV_USER}(기본 {DEFAULT_USER})도 조정 가능"
            )
        self._driver = neo4j.GraphDatabase.driver(
            os.environ.get(ENV_URI, DEFAULT_URI),
            auth=(os.environ.get(ENV_USER, DEFAULT_USER), password),
        )

    def close(self) -> None:
        self._driver.close()

    def replace_project(self, project: str, nodes: list[GraphNode], edges: list[GraphEdge]) -> None:
        node_rows = [{"key": n.key, "kind": n.kind, "props": n.props} for n in nodes]
        edge_rows = [{"kind": e.kind, "src": e.src, "dst": e.dst} for e in edges]
        with self._driver.session() as s:
            s.run("MATCH (n:CodeNode {project:$p}) DETACH DELETE n", p=project)
            s.run(
                "UNWIND $rows AS r CREATE (n:CodeNode {project:$p, key:r.key, kind:r.kind}) "
                "SET n += r.props",
                p=project,
                rows=node_rows,
            )
            s.run(
                "UNWIND $rows AS r "
                "MATCH (a:CodeNode {project:$p, key:r.src}), (b:CodeNode {project:$p, key:r.dst}) "
                "CREATE (a)-[:REL {kind:r.kind}]->(b)",
                p=project,
                rows=edge_rows,
            )

    def neighbors(
        self, project: str, node_key: str, edge_kind: str, direction: str
    ) -> list[GraphNode]:
        if direction == "in":
            cypher = (
                "MATCH (b:CodeNode {project:$p})-[:REL {kind:$k}]->"
                "(a:CodeNode {project:$p, key:$key}) RETURN b"
            )
        else:
            cypher = (
                "MATCH (a:CodeNode {project:$p, key:$key})-[:REL {kind:$k}]->"
                "(b:CodeNode {project:$p}) RETURN b"
            )
        with self._driver.session() as s:
            records = s.run(cypher, p=project, k=edge_kind, key=node_key)
            return [_to_node(r["b"]) for r in records]

    def methods_by_kind(self, project: str, is_test: bool) -> list[GraphNode]:
        with self._driver.session() as s:
            records = s.run(
                "MATCH (n:CodeNode {project:$p, kind:'Method'}) "
                "WHERE coalesce(n.is_test, false) = $t RETURN n",
                p=project,
                t=is_test,
            )
            return [_to_node(r["n"]) for r in records]


def _to_node(record) -> GraphNode:
    props = dict(record)
    key = props.pop("key")
    kind = props.pop("kind")
    props.pop("project", None)
    return GraphNode(kind=kind, key=key, props=props)
