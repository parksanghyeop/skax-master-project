"""호출 관계(CALLS) 추정과 영향 범위의 단위 테스트 (ADR-0026 D1·D2).

검증: 확신도 규칙(같은 클래스 high · 선언 타입 high · 이름 유일 medium · 중복은 엣지 없음 ·
생성자·주석·문자열은 무시), callers 쿼리 답의 "추정" 표기, 폴백(그래프 DB 없음)도 답한다,
그리고 데모 프로젝트 실측(ADR-0026 검증 계획). Neo4j·Docker 없이 돈다.
"""

from pathlib import Path

from cta.adapters.java.calls import ClassSource, StaticImpactFinder, extract_calls
from cta.adapters.java.graph_builder import build_graph
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.parsing import extract_methods
from cta.adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph
from cta.core.tools.query_code_graph import query_code_graph
from cta.graph.answers import GraphCodeGraph
from cta.graph.impact import GraphImpactFinder
from cta.graph.model import CALLS_HIGH, CALLS_MEDIUM, EDGE_CALLS
from cta.graph.store import InMemoryGraphStore

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"

SERVICE = """\
public class Service {
    private final Repo repo;
    public Item load(Long id) { return repo.find(id); }
    public Item pay(Long id) {
        Item item = load(id);          // 같은 클래스 → high
        item.markPaid();               // 선언 타입 Item → high
        helper.format(item);           // 타입 미상, 이름 유일 → medium
        other.load(id);                // 타입 미상, 이름 중복(Service·Other) → 엣지 없음
        String s = "load(" + "x";     // 문자열 안은 무시
        // load(id) 주석 안은 무시
        return new Item(id);           // 생성자는 호출이 아니다
    }
}
"""
ITEM = """\
public class Item {
    public void markPaid() { }
    public Item(Long id) { }
}
"""
OTHER = """\
public class Other {
    public Item load(Long id) { return null; }
}
"""
FORMATTER = """\
public class Formatter {
    public String format(Item item) { return ""; }
}
"""


def _classes(**sources: str) -> list[ClassSource]:
    return [ClassSource(name, src, extract_methods(src)) for name, src in sources.items()]


def _by_pair(edges):
    return {(e.src, e.dst): e for e in edges}


class TestExtractCalls:
    def test_같은_클래스_호출과_선언_타입_호출은_high(self):
        edges = _by_pair(
            extract_calls(_classes(Service=SERVICE, Item=ITEM, Other=OTHER, Formatter=FORMATTER))
        )
        assert edges[("Service#pay", "Service#load")].confidence == CALLS_HIGH
        assert edges[("Service#pay", "Item#markPaid")].confidence == CALLS_HIGH
        assert edges[("Service#pay", "Service#load")].excerpt == "Item item = load(id);"

    def test_타입_미상이면_이름이_유일할_때만_medium(self):
        edges = _by_pair(
            extract_calls(_classes(Service=SERVICE, Item=ITEM, Other=OTHER, Formatter=FORMATTER))
        )
        assert edges[("Service#pay", "Formatter#format")].confidence == CALLS_MEDIUM
        # `other.load(` — load는 Service·Other 둘 다 가지므로 추측하지 않는다
        assert ("Service#pay", "Other#load") not in edges

    def test_생성자_주석_문자열은_호출로_치지_않는다(self):
        edges = _by_pair(extract_calls(_classes(Service=SERVICE, Item=ITEM)))
        assert all(dst != "Item#Item" for _, dst in edges)
        # 주석·문자열 안의 load( 는 발췌에 나타나지 않는다 — 코드 줄만 잡힌다
        assert edges[("Service#pay", "Service#load")].excerpt == "Item item = load(id);"

    def test_프로젝트_밖_타입의_메서드는_이름이_같아도_엣지가_없다(self):
        src = """\
public class Calc {
    public int add(int a, int b) { return a + b; }
    public int sum(List<Integer> xs) { List<Integer> list = xs; list.add(1); return 0; }
}
"""
        edges = extract_calls(_classes(Calc=src))
        assert edges == []  # list의 타입 List는 프로젝트 클래스가 아니다 — medium으로 새지 않는다

    def test_자기_자신_호출은_뺀다(self):
        src = "public class R { public int f(int n) { return n == 0 ? 0 : f(n - 1); } }\n"
        assert extract_calls(_classes(R=src)) == []


class TestCallersAnswer:
    def _graph(self):
        classes = _classes(Service=SERVICE, Item=ITEM, Other=OTHER, Formatter=FORMATTER)
        store = InMemoryGraphStore()
        nodes = []
        from cta.graph.model import NODE_METHOD, GraphNode

        for c in classes:
            for m in c.methods:
                nodes.append(GraphNode(NODE_METHOD, f"{c.name}#{m.name}", {"class_name": c.name}))
        store.replace_project("p", nodes, extract_calls(classes))
        return GraphCodeGraph(store, "p"), store

    def test_답에_추정_표기와_확신도가_들어가고_high가_먼저다(self):
        graph, _ = self._graph()
        answer = query_code_graph(graph, "callers", "Service#load")
        assert "정적 추정" in answer and "Service#pay [high]" in answer
        assert "inspect_target" in answer  # 추정이니 확인하라는 안내

    def test_호출자가_없으면_없다고_말한다(self):
        graph, _ = self._graph()
        answer = graph.answer("callers", "Service#pay")
        assert "없음" in answer and "정적 추정" in answer

    def test_ImpactFinder는_확신_높은_순의_Caller_목록을_준다(self):
        _, store = self._graph()
        callers = GraphImpactFinder(store, "p").find("Service#load")
        assert [(c.target, c.confidence) for c in callers] == [("Service#pay", CALLS_HIGH)]
        assert callers[0].excerpt == "Item item = load(id);"


class TestDemoProjectMeasured:
    """ADR-0026 검증 계획의 실측 항목 — 데모 프로젝트에서 기대한 호출자가 정확히 나온다."""

    def test_findById_호출자는_같은_클래스_3곳과_컨트롤러_1곳이다(self):
        project = detect_maven_project(DEMO)
        nodes, edges = build_graph(project)
        callers = sorted(
            (e.src, e.confidence)
            for e in edges
            if e.kind == EDGE_CALLS and e.dst == "OrderService#findById"
        )
        assert callers == [
            ("OrderController#get", CALLS_HIGH),
            ("OrderService#cancel", CALLS_HIGH),
            ("OrderService#pay", CALLS_HIGH),
            ("OrderService#updateAmount", CALLS_HIGH),
        ]

    def test_테스트_트리는_CALLS의_출발점이_아니다(self):
        _, edges = build_graph(detect_maven_project(DEMO))
        assert not any(
            e.src.endswith("Test") or "Test#" in e.src for e in edges if e.kind == EDGE_CALLS
        )

    def test_그래프_DB_없이도_폴백이_callers에_답한다(self):
        project = detect_maven_project(DEMO)
        graph = ParsingCodeGraph(JavaSimilarTestFinder(project), project)
        assert "OrderController#cancel [high]" in graph.answer("callers", "OrderService#cancel")
        finder = StaticImpactFinder(project)
        assert [c.target for c in finder.find("OrderService#cancel")] == ["OrderController#cancel"]
        assert finder.find("OrderService#total") == []
