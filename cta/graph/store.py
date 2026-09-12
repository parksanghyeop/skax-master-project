"""그래프 저장소 인터페이스와 인메모리 구현.

저장소는 "무엇을 저장하고 어떻게 찾나"만 안다 — 답 문장을 만드는 것은
answers.py의 몫이다. 인메모리 구현은 단위 테스트와 소규모 1회성 실행
(그래프 DB 없이 파이프라인 돌리기)에 쓰고, 실물은 neo4j_store.py.
"""

from typing import Protocol

from cta.graph.model import GraphEdge, GraphNode


class GraphStore(Protocol):
    """프로젝트 단위로 그래프를 통째로 교체·조회하는 포트.

    replace_project: 해당 프로젝트의 기존 노드·엣지를 지우고 새로 넣는다.
      (변경 파일만 갱신하는 증분 방식은 M5의 변경 추출과 함께 도입 예정)
    neighbors: node_key에 연결된 이웃을 엣지 종류·방향으로 찾는다.
    methods_by_kind: kind·is_test로 메서드 노드를 모아 온다(모양 비교는 호출부가).
    edges_in: node_key로 들어오는 엣지 자체를 돌려준다 — 확신도·발췌가 엣지에 있는
      CALLS(ADR-0026)처럼 이웃 노드만으로는 부족할 때 쓴다.
    """

    def replace_project(
        self, project: str, nodes: list[GraphNode], edges: list[GraphEdge]
    ) -> None: ...

    def neighbors(
        self, project: str, node_key: str, edge_kind: str, direction: str
    ) -> list[GraphNode]: ...

    def methods_by_kind(self, project: str, is_test: bool) -> list[GraphNode]: ...

    def edges_in(self, project: str, node_key: str, edge_kind: str) -> list[GraphEdge]: ...


class InMemoryGraphStore:
    """딕셔너리 기반 저장소 — 프로세스 안에서만 산다 (GraphStore 구현)."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, GraphNode]] = {}  # project -> key -> node
        self._edges: dict[str, list[GraphEdge]] = {}  # project -> edges

    def replace_project(self, project: str, nodes: list[GraphNode], edges: list[GraphEdge]) -> None:
        self._nodes[project] = {n.key: n for n in nodes}
        self._edges[project] = list(edges)

    def neighbors(
        self, project: str, node_key: str, edge_kind: str, direction: str
    ) -> list[GraphNode]:
        """direction "in": node_key로 들어오는 엣지의 출발점들, "out": 나가는 엣지의 도착점들."""
        nodes = self._nodes.get(project, {})
        result = []
        for e in self._edges.get(project, []):
            if e.kind != edge_kind:
                continue
            if direction == "in" and e.dst == node_key and e.src in nodes:
                result.append(nodes[e.src])
            elif direction == "out" and e.src == node_key and e.dst in nodes:
                result.append(nodes[e.dst])
        return result

    def methods_by_kind(self, project: str, is_test: bool) -> list[GraphNode]:
        return [
            n
            for n in self._nodes.get(project, {}).values()
            if n.kind == "Method" and bool(n.props.get("is_test")) == is_test
        ]

    def edges_in(self, project: str, node_key: str, edge_kind: str) -> list[GraphEdge]:
        """node_key로 들어오는 edge_kind 엣지들 (출발 노드가 그래프에 있는 것만)."""
        nodes = self._nodes.get(project, {})
        return [
            e
            for e in self._edges.get(project, [])
            if e.kind == edge_kind and e.dst == node_key and e.src in nodes
        ]
