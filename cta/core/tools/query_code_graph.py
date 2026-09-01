"""도구 2/6 query_code_graph — 코드 그래프에 사전 정의 쿼리를 보낸다 (v4 3절, ADR-0009).

자유 쿼리는 금지 — 미리 정의된 쿼리 이름만 받는다(v4 3절 주의 1).
M4부터 그래프 실물(CodeGraph 포트)이 답한다. 확정 엣지 3종으로 답하는 쿼리는
실응답, 나머지는 안내 문장(구현체·바깥세상·호출은 후순위).
"""

from cta.core.ports import CodeGraph
from cta.core.textlimit import clip

# v4 4.1 ③의 쿼리 6종 이름. 원천 목록 — contracts.md가 이 상수를 참조한다.
QUERY_SIMILAR_TESTS = "similar_tests"
KNOWN_QUERIES = (
    "callers",  # 호출하는 곳은? (CALLS 후순위)
    "verifying_tests",  # 검증하는 테스트는? (COVERS 실측)
    "how_to_create",  # 만드는 방법은? (CREATES)
    "implementations",  # 구현체는? (후순위)
    "touches_outside",  # 바깥세상에 닿나? (후순위)
    QUERY_SIMILAR_TESTS,  # 비슷한 모양의 테스트는?
)

# 그래프 답 상한 ≈ 800토큰 (phase2 스킬. 문자 수 환산: 대략 토큰×4)
GRAPH_ANSWER_MAX_CHARS = 3200


def query_code_graph(graph: CodeGraph, query: str, target: str) -> str:
    """사전 정의 쿼리를 실행한다. 모르는 쿼리도 예외가 아니라 안내 문자열이다."""
    if query not in KNOWN_QUERIES:
        return clip(f"모르는 쿼리 {query!r}. 허용 목록: {', '.join(KNOWN_QUERIES)}")
    return clip(graph.answer(query, target), GRAPH_ANSWER_MAX_CHARS)
