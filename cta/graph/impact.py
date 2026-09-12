"""영향 범위 찾기 — CALLS 엣지에서 호출자 목록을 만드는 ImpactFinder 구현 (ADR-0026 D1).

저장소가 어디든(Neo4j·인메모리) 같은 코드다. 답 문장은 answers.py의 callers 쿼리가,
구조화된 목록(화면·지침서·파생 생성 건)은 이 모듈이 담당한다. 층: graph.
"""

from cta.core.pipeline.models import Caller
from cta.graph.model import CALLS_HIGH, CALLS_MEDIUM, EDGE_CALLS
from cta.graph.store import GraphStore

_CONFIDENCE_RANK = {CALLS_HIGH: 0, CALLS_MEDIUM: 1}


class GraphImpactFinder:
    """그래프의 CALLS 엣지로 호출자를 찾는다 (ImpactFinder 구현). 확신 높은 것부터 정렬."""

    def __init__(self, store: GraphStore, project_key: str) -> None:
        self._store = store
        self._project_key = project_key

    def find(self, target: str) -> list[Caller]:
        edges = self._store.edges_in(self._project_key, target, EDGE_CALLS)
        ranked = sorted(edges, key=lambda e: (_CONFIDENCE_RANK.get(e.confidence, 9), e.src))
        return [Caller(target=e.src, confidence=e.confidence, excerpt=e.excerpt) for e in ranked]
