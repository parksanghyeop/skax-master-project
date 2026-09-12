"""코드 그래프의 데이터 모델 — 노드·엣지의 언어 무관 표현.

v4 4.1 ①의 노드 2종·엣지 4종 — 확정 3종 + 추정 1종(CALLS, 확신도 필수, ADR-0026).
시그니처를 바꾸면 docs/contracts.md를 같은 커밋에서 갱신한다.
"""

from dataclasses import dataclass, field

from cta.core.pipeline.models import CONFIDENCE_HIGH, CONFIDENCE_MEDIUM

# 노드 종류. TestMethod를 따로 두지 않고 Method의 is_test 속성으로 구분한다 —
# "테스트도 메서드다"가 질의(모양 비교)를 단순하게 만든다.
NODE_CLASS = "Class"
NODE_METHOD = "Method"

# 확정 엣지 3종 (v4 4.1: 코드를 읽거나 실측해서 100% 확정되는 관계만)
EDGE_DECLARES = "DECLARES"  # 클래스 → 메서드
EDGE_CREATES = "CREATES"  # 메서드 → (그 몸통에서 생성하는) 클래스
EDGE_COVERS = "COVERS"  # 테스트 클래스 → (실행이 실측된) 메서드, 근거는 커버리지 기록

# 추정 엣지 1종 (v4 4.1 ① "호출한다 — 추정하되 확신도를 함께 기록", ADR-0026 D1).
# 규칙표·기존 테스트 상태 판정에는 쓰지 않는다 — 화면·지침서·파생 생성 건 전용(ADR-0026 D2).
EDGE_CALLS = "CALLS"  # 메서드 → (그 몸통에서 부르는) 메서드. confidence 필수
CALLS_HIGH = CONFIDENCE_HIGH  # 타입이 소스에서 읽힘 (같은 클래스 / 선언 타입이 프로젝트 클래스)
CALLS_MEDIUM = CONFIDENCE_MEDIUM  # 타입 미확인이지만 메서드 이름이 프로젝트에서 유일

# 노드에 저장하는 소스 발췌 상한. 그래프 답은 "짧은 요약"이어야 한다(v4 4.1 ③) —
# 원문 전체가 필요하면 에이전트가 inspect_target으로 따로 본다.
SNIPPET_MAX_CHARS = 600


@dataclass(frozen=True)
class GraphNode:
    """그래프 노드 하나. key는 프로젝트 안에서 유일한 식별자.

    key 규칙: 클래스 = "Calculator", 메서드 = "Calculator#divide".
    오버로드(같은 이름, 다른 파라미터)는 key가 겹친다 — 알려진 한계로 기록,
    필요해지면 파라미터 시그니처를 key에 넣는다.
    """

    kind: str  # NODE_CLASS | NODE_METHOD
    key: str
    props: dict = field(default_factory=dict)
    # Method props: class_name, name, param_count(int), uses_exception(bool),
    #               is_test(bool), snippet(str)
    # Class props:  package, is_test(bool)


@dataclass(frozen=True)
class GraphEdge:
    """방향 있는 엣지. kind는 확정 3종 또는 CALLS.

    confidence: CALLS에만 있다(CALLS_HIGH/MEDIUM). 확정 3종은 빈 문자열 — "확정"은
      확신도가 없다는 뜻이 아니라 붙일 필요가 없다는 뜻이다.
    excerpt: CALLS의 호출 줄 발췌 한 줄(지침서용). 다른 엣지는 빈 문자열.
    dict가 아니라 문자열 필드인 이유: frozen dataclass가 set·정렬(빌더의 중복 제거)에 그대로
      쓰이려면 해시 가능해야 한다.
    """

    kind: str
    src: str  # 출발 노드 key
    dst: str  # 도착 노드 key
    confidence: str = ""
    excerpt: str = ""
