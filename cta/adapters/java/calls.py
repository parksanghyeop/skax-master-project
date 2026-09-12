"""Java 소스에서 호출 관계(CALLS)를 추정한다 — 확신도를 붙인 엣지 (ADR-0026 D1).

"이 메서드를 누가 호출하나"(영향 범위)의 정적 추정. 상속·다형성·리플렉션 때문에 정적으로
100% 확정이 안 되므로(v4 4.1 ①) 엣지마다 확신도를 붙이고, 확신이 없는 후보는 만들지 않는다
— 없는 것이 틀린 것보다 낫다(코드그래프.md 3절). 전부 정규식이며 LLM은 없다.
main 소스만 본다 — 테스트→코드 관계는 COVERS(커버리지 실측)가 담당한다.
층: adapters/java (언어를 아는 쪽이 그래프를 채운다).

| 호출 모양 | 확신도 |
|---|---|
| 같은 클래스 안의 `이름(` (수식 없음) | high |
| `x.이름(` 이고 x의 선언 타입이 프로젝트 클래스 X, X에 `이름`이 있다 | high |
| `x.이름(` 이고 타입은 못 읽었지만 `이름`을 가진 프로젝트 클래스가 하나뿐 | medium |
| 그 밖 (타입이 프로젝트 밖·이름 중복·타입은 읽혔는데 그 클래스에 없음) | 엣지 없음 |
"""

import re
from dataclasses import dataclass

from cta.adapters.java.parsing import JavaMethod
from cta.graph.model import CALLS_HIGH, CALLS_MEDIUM, EDGE_CALLS, GraphEdge

# 호출 줄 발췌 상한 — 지침서에 "어떻게 부르는지" 한 줄이면 충분하다
EXCERPT_MAX_CHARS = 120

# `x.이름(` — 수신자 한 단어 + 메서드 이름.
# 체인(`a.b().c(`)의 두 번째 호출은 수신자가 `)`라 안 잡힌다(의도)
_QUALIFIED_CALL = re.compile(r"\b(\w+)\s*\.\s*(\w+)\s*\(")
# `이름(` — 앞에 단어·점이 없는 것만(수식 없는 호출).
# `new X(`의 X도 잡히지만 클래스 이름이라 버려진다
_UNQUALIFIED_CALL = re.compile(r"(?<![\w.])(\w+)\s*\(")
# `Type name` 선언 — 필드·파라미터·지역변수·for-each. 뒤가 `(`이면 메서드 선언이라 제외한다
_DECLARATION = re.compile(r"\b([A-Z]\w*)(?:<[^>]*>)?(?:\[\])?\s+(\w+)\s*(?=[;=,):])")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
# 호출 모양이지만 메서드 호출이 아닌 것. this(/super(는 생성자 호출이라 영향 범위가 아니다
_NOT_CALLS = frozenset("if for while switch catch synchronized return new this super throw".split())
# 확신도 순위 — 같은 (호출자, 대상)에 두 근거가 잡히면 높은 쪽을 남긴다
_RANK = {CALLS_HIGH: 0, CALLS_MEDIUM: 1}


@dataclass(frozen=True)
class ClassSource:
    """추출기 입력 — 클래스 하나의 이름·소스·파싱된 메서드 (빌더가 만들어 넘긴다)."""

    name: str
    source: str
    methods: list[JavaMethod]


def extract_calls(classes: list[ClassSource]) -> list[GraphEdge]:
    """main 클래스들 사이의 CALLS 엣지를 추정한다.

    입력: 프로젝트 main 트리의 클래스들(테스트 제외).
    출력: (호출자, 대상)로 중복 제거되고 정렬된 CALLS 엣지. 자기 자신 호출(재귀)은 뺀다 —
      영향 범위로서 의미가 없다. 파싱이 안 되는 곳은 조용히 건너뛴다(그래프는 보조 정보).
    """
    class_names = {c.name for c in classes}
    owners: dict[str, set[str]] = {}  # 메서드 이름 → 그 이름을 선언한 클래스들
    for c in classes:
        for m in c.methods:
            owners.setdefault(m.name, set()).add(c.name)

    edges: dict[tuple[str, str], GraphEdge] = {}
    for c in classes:
        # 변수 이름 → 선언 타입. 클래스 전체에서 모으므로 같은 이름이 다른 타입으로 두 번
        # 선언되면 나중 것이 이긴다 — 알려진 한계(실무에서 드물다)
        declared = _declared_types(_strip(c.source))
        for m in c.methods:
            src = f"{c.name}#{m.name}"
            # 흐름: 주석·문자열 제거 → 줄마다 수식·비수식 호출 추출 → 확신도 판정 → 높은 쪽만 유지
            for line in _strip(m.text).splitlines():
                for receiver, name in _QUALIFIED_CALL.findall(line):
                    resolved = _resolve(c.name, receiver, name, declared, class_names, owners)
                    if resolved is not None:
                        _keep(edges, src, resolved[0], resolved[1], line)
                for name in _UNQUALIFIED_CALL.findall(line):
                    # 클래스 이름과 같으면 생성자 호출(`new Order(`)이다 — 영향 범위가 아니다
                    if name in _NOT_CALLS or name == m.name or name in class_names:
                        continue
                    if c.name in owners.get(name, ()):
                        _keep(edges, src, f"{c.name}#{name}", CALLS_HIGH, line)
    return sorted((e for e in edges.values() if e.src != e.dst), key=lambda e: (e.dst, e.src))


def _resolve(
    class_name: str,
    receiver: str,
    name: str,
    declared: dict[str, str],
    class_names: set[str],
    owners: dict[str, set[str]],
) -> tuple[str, str] | None:
    """`receiver.name(` 이 가리키는 (대상 key, 확신도). 판정 불가면 None."""
    if receiver == "this":
        owner = class_name
    elif receiver in class_names:  # 정적 호출 `Foo.bar(`
        owner = receiver
    else:
        owner = declared.get(receiver)
    if owner is not None:
        # 타입을 읽었다: 프로젝트 클래스가 그 메서드를 선언했을 때만 high.
        # 프로젝트 밖 타입(List 등)이거나 선언이 없으면(인터페이스 추상 메서드·Lombok 생성)
        # 엣지 없음
        if owner in class_names and owner in owners.get(name, ()):
            return f"{owner}#{name}", CALLS_HIGH
        return None
    candidates = owners.get(name, set())
    if len(candidates) == 1:  # 타입은 모르지만 이름이 프로젝트에서 유일 — medium
        return f"{next(iter(candidates))}#{name}", CALLS_MEDIUM
    return None


def _keep(edges: dict, src: str, dst: str, confidence: str, line: str) -> None:
    key = (src, dst)
    current = edges.get(key)
    if current is not None and _RANK[current.confidence] <= _RANK[confidence]:
        return
    edges[key] = GraphEdge(
        kind=EDGE_CALLS,
        src=src,
        dst=dst,
        confidence=confidence,
        excerpt=line.strip()[:EXCERPT_MAX_CHARS],
    )


def _declared_types(source: str) -> dict[str, str]:
    """`Type name` 선언에서 변수 이름 → 타입. 제네릭 인자·배열 표기는 벗긴다."""
    return {name: type_name for type_name, name in _DECLARATION.findall(source)}


def _strip(source: str) -> str:
    """주석·문자열 리터럴을 지운다 — 그 안의 `foo(` 모양이 호출로 잡히지 않게."""
    without_comments = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))
    return _STRING.sub('""', without_comments)


class StaticImpactFinder:
    """그래프 저장소 없이 그 자리에서 파싱해 호출자를 찾는다 (ImpactFinder 구현, 폴백).

    첫 질의 때 프로젝트 전체를 한 번 파싱하고 재사용한다 — maintain이 변경 건마다 부르므로.
    """

    def __init__(self, project) -> None:
        self._project = project
        self._finder = None

    def find(self, target: str):
        if self._finder is None:
            from cta.adapters.java.graph_builder import build_graph
            from cta.graph.impact import GraphImpactFinder
            from cta.graph.store import InMemoryGraphStore

            nodes, edges = build_graph(self._project)
            store = InMemoryGraphStore()
            store.replace_project("static", nodes, edges)
            self._finder = GraphImpactFinder(store, "static")
        return self._finder.find(target)
