"""고유 도구 6개 + ask_user를 LangChain 도구로 감싼다 (ADR-0025 결정 4).

본체는 `core/tools/`의 함수들이다 — 길이 상한(clip)·"예외 대신 문장" 규약은 거기서 지킨다.
여기서는 포트를 클로저로 닫고 설명(모델이 읽는 도구 설명)만 단다.
층: core — 포트만 안다. 도구 이름은 v4 3절·contracts.md의 코드 식별자와 같다.
"""

from langchain_core.tools import BaseTool, tool

from cta.core import tools as core_tools
from cta.core.agent.limits import REPLY_STOP_PREFIX
from cta.core.agent.ports import AgentPorts
from cta.core.tools.query_code_graph import KNOWN_QUERIES

# 고유 도구 이름 — R4의 6개. tests/test_agent_deep.py가 이 집합을 고정한다.
NATIVE_TOOL_NAMES = frozenset(
    {
        "inspect_target",
        "query_code_graph",
        "write_test",
        "run_tests",
        "check_quality",
        "report_finding",
    }
)
ASK_USER_TOOL = "ask_user"  # 사람 개입 장치 — 고유 도구가 아니다(ADR-0025 결정 3)

_QUERY_DESCRIPTION = (
    "코드 그래프 조회 — 미리 정의된 쿼리만 허용한다(자유 쿼리 금지). "
    f"query는 다음 중 하나: {', '.join(KNOWN_QUERIES)}. target은 대상 식별자."
)


def make_tools(ports: AgentPorts) -> dict[str, BaseTool]:
    """포트를 닫아 넣은 도구 7개(고유 6 + ask_user)를 이름 → 도구로 돌려준다."""

    @tool
    def inspect_target(target: str) -> str:
        """대상 조사 — 테스트할 메서드의 형태·의존하는 것·기존 테스트 요약을 돌려준다.
        target: "클래스" 또는 "클래스#메서드" 또는 "클래스#메서드1,메서드2"."""
        ports.progress(f"대상 조사 — {target}")
        return core_tools.inspect_target(ports.inspector, target)

    @tool(description=_QUERY_DESCRIPTION)
    def query_code_graph(query: str, target: str) -> str:
        return core_tools.query_code_graph(ports.graph, query, target)

    @tool
    def write_test(path: str, code: str) -> str:
        """테스트 쓰기 — 테스트 파일을 만들거나 통째로 바꾼다. path는 작업 지침의
        "테스트 파일 경로"를 그대로 쓴다(테스트 폴더 밖은 거부된다). code는 파일 전체 내용.
        반환은 컴파일·정적 검사 결과다."""
        ports.progress(f"테스트 쓰기 — {len(code)}자")
        return core_tools.write_test(ports.writer, path, code)

    @tool
    def run_tests(selector: str) -> str:
        """테스트 실행 — 지정한 테스트만 실행 장치에서 돌린다(전체 실행 금지).
        selector는 작업 지침의 "실행 selector"를 그대로 쓴다. 반환 선두가 "통과"면 성공이다."""
        ports.progress(f"테스트 실행 — {selector}")
        return core_tools.run_tests(ports.runner, selector)

    @tool
    def check_quality(path: str) -> str:
        """품질 확인 — 완성된 테스트 파일의 기계적 검사 결과를 돌려준다.
        테스트가 통과한 뒤 부른다."""
        return core_tools.check_quality(ports.checker, path)

    @tool
    def report_finding(finding: str) -> str:
        """한계 보고 — "이래서 통과시킬 수 없다"를 정리해 제출하고 작업을 끝낸다.
        부른 뒤에는 더 시도하지 않는다."""
        ports.progress("한계 보고")
        return core_tools.report_finding(finding)

    @tool
    def ask_user(question: str) -> str:
        """사용자에게 묻기 — 판단이 필요한 실패나 반복 한도에서 멈추고 사람의 답
        (계속/중지/힌트)을 받는다. 답이 "중지"면 report_finding으로 끝내라."""
        reply = ports.gate.ask(question)
        if reply.action == "stop":
            return f"{REPLY_STOP_PREFIX} — 더 시도하지 말고 report_finding으로 한계를 보고하라."
        hint = reply.hint.strip() if reply.hint else ""
        return f"사용자 답: 계속. 힌트: {hint or '(없음)'}"

    made = [
        inspect_target,
        query_code_graph,
        write_test,
        run_tests,
        check_quality,
        report_finding,
        ask_user,
    ]
    return {t.name: t for t in made}
