"""그래프 계층(모델·인메모리 저장소·빌더·질의 응답·커버리지 파서)의 단위 테스트.

Neo4j·Docker 없이 돈다 — 실물 Neo4j 왕복은 tests/test_graph_neo4j.py(neo4j 마커).
"""

from pathlib import Path

from adapters.java.coverage import parse_covered_methods
from adapters.java.graph_builder import build_graph
from adapters.java.maven import detect_maven_project
from graph.answers import GraphCodeGraph
from graph.model import EDGE_COVERS, EDGE_CREATES, EDGE_DECLARES, GraphEdge
from graph.store import InMemoryGraphStore

MAIN = """\
package com.example;

public class Calc {
    public int add(int a, int b) { return a + b; }

    public int divide(int a, int b) {
        if (b == 0) { throw new IllegalArgumentException("no"); }
        return a / b;
    }
}
"""

HELPER = """\
package com.example;

public class CalcFactory {
    public Calc standard() { return new Calc(); }
}
"""

TEST = """\
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalcTest {
    @Test
    void add_twoPositives_returnsSum() {
        Calc calc = new Calc();
        assertEquals(7, calc.add(3, 4));
    }
}
"""

JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="demo">
  <package name="com/example">
    <class name="com/example/Calc" sourcefilename="Calc.java">
      <method name="&lt;init&gt;" desc="()V" line="3">
        <counter type="LINE" missed="0" covered="1"/>
      </method>
      <method name="add" desc="(II)I" line="4">
        <counter type="INSTRUCTION" missed="0" covered="4"/>
        <counter type="LINE" missed="0" covered="1"/>
      </method>
      <method name="divide" desc="(II)I" line="6">
        <counter type="LINE" missed="3" covered="0"/>
      </method>
    </class>
  </package>
</report>
"""


def _project(tmp_path: Path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    main = tmp_path / "src" / "main" / "java" / "com" / "example"
    test = tmp_path / "src" / "test" / "java" / "com" / "example"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    (main / "Calc.java").write_text(MAIN, encoding="utf-8")
    (main / "CalcFactory.java").write_text(HELPER, encoding="utf-8")
    (test / "CalcTest.java").write_text(TEST, encoding="utf-8")
    return detect_maven_project(tmp_path)


class TestGraphBuilder:
    def test_클래스와_메서드_노드를_만든다(self, tmp_path):
        nodes, _ = build_graph(_project(tmp_path))
        keys = {n.key for n in nodes}
        assert {"Calc", "Calc#add", "Calc#divide", "CalcFactory#standard", "CalcTest"} <= keys

    def test_DECLARES와_CREATES_엣지를_만든다(self, tmp_path):
        _, edges = build_graph(_project(tmp_path))
        assert GraphEdge(EDGE_DECLARES, "Calc", "Calc#divide") in edges
        # CalcFactory.standard와 CalcTest의 테스트 메서드가 Calc를 생성한다
        assert GraphEdge(EDGE_CREATES, "CalcFactory#standard", "Calc") in edges
        assert GraphEdge(EDGE_CREATES, "CalcTest#add_twoPositives_returnsSum", "Calc") in edges

    def test_테스트_메서드는_is_test_속성을_가진다(self, tmp_path):
        nodes, _ = build_graph(_project(tmp_path))
        by_key = {n.key: n for n in nodes}
        assert by_key["CalcTest#add_twoPositives_returnsSum"].props["is_test"] is True
        assert by_key["Calc#add"].props["is_test"] is False


class TestGraphAnswers:
    def _graph(self, tmp_path, extra_edges=()):
        project = _project(tmp_path)
        nodes, edges = build_graph(project)
        store = InMemoryGraphStore()
        store.replace_project("p", nodes, edges + list(extra_edges))
        return GraphCodeGraph(store, "p")

    def test_만드는_방법은_테스트_코드를_우선한다(self, tmp_path):
        answer = self._graph(tmp_path).answer("how_to_create", "Calc")
        assert answer.index("[테스트] CalcTest#") < answer.index("[일반 코드] CalcFactory#")

    def test_검증하는_테스트는_실측_COVERS에서_나온다(self, tmp_path):
        covers = [GraphEdge(EDGE_COVERS, "CalcTest", "Calc#add")]
        answer = self._graph(tmp_path, covers).answer("verifying_tests", "Calc#add")
        assert "CalcTest" in answer and "실측" in answer

    def test_실측_기록이_없으면_그_사실을_말한다(self, tmp_path):
        answer = self._graph(tmp_path).answer("verifying_tests", "Calc#divide")
        assert "실측" in answer and "없" in answer

    def test_비슷한_모양의_테스트를_모양_거리로_고른다(self, tmp_path):
        answer = self._graph(tmp_path).answer("similar_tests", "Calc#divide")
        assert "본보기" in answer and "add_twoPositives_returnsSum" in answer

    def test_후순위_쿼리는_안내_문장이다(self, tmp_path):
        answer = self._graph(tmp_path).answer("callers", "Calc#add")
        assert "inspect_target" in answer


class TestJacocoParser:
    def test_라인이_커버된_메서드만_뽑고_생성자는_제외한다(self):
        covered = parse_covered_methods(JACOCO_XML)
        assert covered == {"Calc#add"}  # divide는 covered=0, <init>은 제외
