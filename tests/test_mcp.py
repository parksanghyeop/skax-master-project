"""MCP 층 — 핸들러는 cli 함수를 그대로 부르고 출력을 문자열로 돌려준다. SDK 등록은 설치 시만."""

import asyncio

import pytest

from cta.mcp import handlers
from cta.mcp.handlers import EXIT_LINE


def _maven_project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "src" / "test" / "java").mkdir(parents=True)
    return str(tmp_path)


class TestHandlers:
    def test_제안이_없으면_목록_문구와_종료_코드_0(self, tmp_path):
        text = handlers.list_proposals(_maven_project(tmp_path))
        assert "대기 중인 제안 없음" in text
        assert text.rstrip().endswith(f"{EXIT_LINE}: 0")

    def test_출력은_stdout으로_새지_않고_문자열로_돌아온다(self, tmp_path, capsys):
        handlers.list_proposals(_maven_project(tmp_path))
        assert capsys.readouterr().out == ""  # stdio 프로토콜 채널을 더럽히지 않는다

    def test_pom_xml이_없으면_안내_문구와_종료_코드_1(self, tmp_path):
        text = handlers.list_proposals(str(tmp_path))
        assert "--project" in text or "pom.xml" in text
        assert text.rstrip().endswith(f"{EXIT_LINE}: 1")

    def test_resolve의_decision은_네_가지만(self, tmp_path):
        text = handlers.resolve(_maven_project(tmp_path), "maybe")
        assert "intended, test-issue, proceed, skip" in text
        assert text.rstrip().endswith(f"{EXIT_LINE}: 1")

    def test_도구_5개는_전부_docstring과_타입_힌트가_있다(self):
        assert [t.__name__ for t in handlers.TOOLS] == [
            "generate",
            "maintain",
            "resolve",
            "list_proposals",
            "apply",
        ]
        for tool in handlers.TOOLS:
            assert tool.__doc__ and "project" in tool.__annotations__
            assert tool.__annotations__["return"] is str


mcp_sdk = pytest.importorskip("mcp.server.mcpserver", reason="MCP SDK는 선택 의존성")


class TestServer:
    def test_도구_5개가_등록되고_호출이_문자열을_돌려준다(self, tmp_path):
        from cta.mcp.server import build_server

        server = build_server()

        async def scenario():
            tools = await server.list_tools()
            result = await server.call_tool("list_proposals", {"project": _maven_project(tmp_path)})
            return [t.name for t in tools], result

        names, result = asyncio.run(scenario())
        assert names == ["generate", "maintain", "resolve", "list_proposals", "apply"]
        assert result.is_error is False
        assert "대기 중인 제안 없음" in result.content[0].text
