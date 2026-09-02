"""그래프 접속 선택(cli/graph_access) — 설정이 없으면 파싱 폴백, 있어도 접속이 안 되면 폴백."""

from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.similar import ParsingCodeGraph
from cta.cli.graph_access import FALLBACK_NOTE, choose_code_graph, try_open_store


def test_설정이_없으면_폴백이다(tmp_path, monkeypatch):
    monkeypatch.delenv("CTA_NEO4J_PASSWORD", raising=False)
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert try_open_store(str(tmp_path)) is None
    graph, note, store = choose_code_graph(detect_maven_project(tmp_path))
    assert isinstance(graph, ParsingCodeGraph)
    assert note == FALLBACK_NOTE and store is None


def test_서버가_없으면_예외_대신_폴백이다(monkeypatch):
    monkeypatch.setenv("CTA_NEO4J_PASSWORD", "x")
    monkeypatch.setenv("CTA_NEO4J_URI", "bolt://127.0.0.1:1")  # 닫힌 포트
    assert try_open_store("p") is None
