"""MCP 서버 진입점 — `cta-mcp`(stdio). 핸들러 5개를 MCP 도구로 등록한다 (ADR-0018).

MCP SDK(2.x, `mcp.server.mcpserver.MCPServer`)는 선택 의존성이다: `pip install code-test-agent[mcp]`
없으면 설치 안내만 내고 끝난다 — CLI 사용자에게 SDK를 강제하지 않는다.
Claude Code 등록 예: `claude mcp add cta -- cta-mcp` (프로젝트 경로는 도구 인자 project로 매번).
시크릿(게이트웨이 주소·키)은 이 프로세스의 환경변수·.env로만 — 도구 인자로 받지 않는다.
"""

import sys

from cta.mcp import handlers

SERVER_NAME = "cta"
INSTRUCTIONS = (
    "Code Test Agent — Java(Maven) 프로젝트의 테스트를 생성·유지보수한다. "
    "generate/maintain은 수 분 걸린다(Docker 샌드박스 실행). 결과의 '종료 코드' 3은 실패가 아니라 "
    "사람 확인 요청이다 — resolve로 답한다. 소스에 쓰는 도구는 apply 하나다."
)
INSTALL_HINT = (
    "MCP SDK가 없다 — 설치: pip install 'code-test-agent[mcp]'  (또는 pip install 'mcp>=2')"
)


def build_server():
    """MCPServer를 만들고 핸들러 5개를 도구로 등록한다. SDK가 없으면 ImportError."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS)
    for tool in handlers.TOOLS:
        server.add_tool(tool)
    return server


def main() -> int:
    try:
        server = build_server()
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        return 1
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
