"""mcp 층 — Claude Code 등 MCP 클라이언트에서 cta를 도구로 부르는 얇은 껍데기 (ADR-0018).

CLI와 로직을 나누지 않는다: 핸들러(handlers.py)는 cli의 서브커맨드 함수를 그대로 호출하고
화면 출력을 문자열로 돌려준다. MCP SDK는 선택 의존성이다(`pip install code-test-agent[mcp]`) —
server.py만 import한다. 여기의 "도구 5개"는 MCP 노출 단위이고, 에이전트 내부 도구 6개
(R4, core/tools)와는 다른 층이다.
"""
