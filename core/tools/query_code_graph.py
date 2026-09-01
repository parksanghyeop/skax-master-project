"""도구 2/6 query_code_graph — 코드 그래프에 사전 정의 쿼리를 보낸다 (v4 3절, ADR-0009).

자유 쿼리는 금지 — 미리 정의된 쿼리 이름만 받는다(v4 3절 주의 1).
PoC 범위: "비슷한 모양의 테스트는?"(similar_tests)만 파싱 기반 최소본으로 실응답하고,
나머지 쿼리는 그래프가 없다는 안내 문자열을 돌려준다(그래프 실물은 2단계).
"""

from core.ports import SimilarTestFinder
from core.textlimit import clip

# v4 4.1 ③의 쿼리 6종 이름. PoC에서 실응답하는 것은 SIMILAR_TESTS뿐이다.
QUERY_SIMILAR_TESTS = "similar_tests"
KNOWN_QUERIES = (
    "callers",  # 호출하는 곳은?
    "verifying_tests",  # 검증하는 테스트는?
    "how_to_create",  # 만드는 방법은?
    "implementations",  # 구현체는?
    "touches_outside",  # 바깥세상에 닿나?
    QUERY_SIMILAR_TESTS,  # 비슷한 모양의 테스트는?
)


def query_code_graph(finder: SimilarTestFinder, query: str, target: str) -> str:
    """사전 정의 쿼리를 실행한다. 모르는 쿼리도 예외가 아니라 안내 문자열이다."""
    if query == QUERY_SIMILAR_TESTS:
        return clip(finder.find(target))
    if query in KNOWN_QUERIES:
        return clip(
            f"그래프 없음(2단계 예정): 쿼리 {query!r}는 아직 답할 수 없다 — inspect_target을 쓰라"
        )
    return clip(f"모르는 쿼리 {query!r}. 허용 목록: {', '.join(KNOWN_QUERIES)}")
