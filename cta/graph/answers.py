"""그래프 질의 → 답 문장 — CodeGraph 포트의 그래프 기반 구현.

저장소(GraphStore)에서 노드·엣지를 찾아 "짧은 요약" 문장을 만든다(v4 4.1 ③).
답할 수 없는 쿼리도 예외가 아니라 다음 행동을 안내하는 문장이다(도구 공통 규약).
길이 상한은 도구 층(core/tools)이 걸므로 여기서는 내용만 만든다.
"""

from cta.graph.model import EDGE_COVERS, EDGE_CREATES, GraphNode
from cta.graph.store import GraphStore

# 답에 담을 최대 항목 수. 많을수록 토큰만 늘고 행동 유도 효과는 줄어든다(경험칙).
MAX_ITEMS = 5
MAX_SIMILAR = 2  # 본보기는 2개 — 1단계 파싱 기반 구현과 같은 기준


class GraphCodeGraph:
    """확정 엣지 3종으로 답하는 CodeGraph 구현 (쿼리 이름은 core/tools의 목록)."""

    def __init__(self, store: GraphStore, project: str) -> None:
        self._store = store
        self._project = project

    def answer(self, query: str, target: str) -> str:
        handlers = {
            "verifying_tests": self._verifying_tests,
            "how_to_create": self._how_to_create,
            "similar_tests": self._similar_tests,
        }
        if query in handlers:
            return handlers[query](target)
        if query == "callers":
            return (
                "호출 관계(CALLS)는 정적으로 100% 확정이 안 돼 후순위다 — "
                "inspect_target으로 확인하라"
            )
        return f"쿼리 {query!r}는 아직 그래프가 답하지 못한다 — inspect_target을 쓰라"

    def _verifying_tests(self, target: str) -> str:
        """이 메서드를 실제로 실행하는 테스트 — COVERS(커버리지 실측) 엣지에서."""
        tests = self._store.neighbors(self._project, target, EDGE_COVERS, "in")
        if not tests:
            return (
                f"{target}를 실행한다고 실측된 테스트 없음 — "
                "커버리지 수집(build_graph --coverage)을 아직 안 했거나, 정말 테스트가 없다"
            )
        names = ", ".join(sorted(t.key for t in tests)[:MAX_ITEMS])
        return f"{target}를 실제로 실행하는 테스트(커버리지 실측): {names}"

    def _how_to_create(self, target: str) -> str:
        """이 클래스를 생성하는 기존 코드 — CREATES 엣지에서, 테스트 코드 우선."""
        creators = self._store.neighbors(self._project, target, EDGE_CREATES, "in")
        if not creators:
            return f"{target}를 생성하는 기존 코드 없음 — 생성자를 inspect_target으로 직접 확인하라"
        # 테스트 코드가 먼저 — 테스트에서의 생성 방법이 새 테스트에 그대로 재사용된다(v4 4.1 ③)
        creators.sort(key=lambda n: (not n.props.get("is_test", False), n.key))
        parts = []
        for c in creators[:MAX_ITEMS]:
            label = "테스트" if c.props.get("is_test") else "일반 코드"
            snippet = c.props.get("snippet", "")
            parts.append(f"[{label}] {c.key}:\n{snippet}")
        return f"{target}를 생성하는 기존 코드:\n\n" + "\n\n".join(parts)

    def _similar_tests(self, target: str) -> str:
        """모양(파라미터 수·예외 유무)이 닮은 기존 테스트 — few-shot 본보기용."""
        nodes = {n.key: n for n in self._store.methods_by_kind(self._project, is_test=False)}
        shape = nodes.get(target)
        if shape is None:
            return f"대상 없음: {target!r} — 그래프에 그 메서드가 없다 (빌드 누락 여부 확인)"
        candidates = self._store.methods_by_kind(self._project, is_test=True)
        if not candidates:
            return "기존 테스트 없음: 그래프에 테스트 메서드가 없다"
        ranked = sorted(candidates, key=lambda c: (_shape_distance(shape, c), c.key))
        parts = [
            f"본보기 ({c.props.get('class_name', '?')}):\n{c.props.get('snippet', '')}"
            for c in ranked[:MAX_SIMILAR]
        ]
        return "\n\n".join(parts)


def _shape_distance(a: GraphNode, b: GraphNode) -> int:
    """모양 거리 — 파라미터 수 차이 + 예외 유무 불일치(1점). similar.py와 같은 기준."""
    return abs(int(a.props.get("param_count", 0)) - int(b.props.get("param_count", 0))) + (
        1 if bool(a.props.get("uses_exception")) != bool(b.props.get("uses_exception")) else 0
    )
