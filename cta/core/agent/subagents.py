"""서브에이전트 3개의 정의 — explorer(탐색) · writer(작성·실행) · diagnoser(진단) (ADR-0024 결정 2).

누가 어떤 도구를 갖나가 이 파일의 전부다(docs/딥에이전트전환안.md §3.2 도구 배치표):
쓰기·실행은 writer만, 나머지는 읽기 전용, ask_user는 어디에도 없다(메인만). 하네스가 자동으로
붙이는 general-purpose 서브는 같은 이름의 빈 spec으로 덮어써 무력화한다.
층: core — 프롬프트의 언어 이름 빈칸은 호출부가 채운다(R1).
"""

from pathlib import Path
from string import Template

from langchain_core.tools import BaseTool

from cta.core.agent.limits import HideWriteTools, RunLedger
from cta.core.agent.ports import AgentPorts

PROMPTS_DIR = Path(__file__).parent / "prompts"

EXPLORER = "explorer"
WRITER = "writer"
DIAGNOSER = "diagnoser"
GENERAL_PURPOSE = "general-purpose"  # 하네스 기본 서브 — 덮어써서 끈다

# 서브별 고유 도구 배치. 이 표가 바뀌면 contracts.md와 test_agent_deep의 불변식도 바뀐다.
SUBAGENT_TOOLS: dict[str, tuple[str, ...]] = {
    EXPLORER: ("inspect_target", "query_code_graph"),
    WRITER: ("write_test", "run_tests"),
    DIAGNOSER: ("inspect_target", "query_code_graph"),
    GENERAL_PURPOSE: (),
}

_DESCRIPTIONS = {
    EXPLORER: (
        "코드 탐색 — 대상 메서드의 형태·의존·생성법·비슷한 기존 테스트를 정해진 형식으로 "
        "보고한다(읽기 전용)"
    ),
    WRITER: (
        "테스트 작성·실행 — 지침서와 조사 보고로 테스트를 쓰고 컴파일·실행해 결과를 보고한다"
        "(쓰기·실행이 있는 유일한 서브)"
    ),
    DIAGNOSER: (
        "실패 진단 — 반복되는 실패의 원인을 소스와 대조해 수정 지시 또는 '사람 판단 필요'를 "
        "보고한다(읽기 전용)"
    ),
    GENERAL_PURPOSE: "쓰지 않는다 — explorer / writer / diagnoser 중 하나를 골라라",
}


def load_prompt(name: str, **fields: str) -> str:
    """prompts/<name>.md를 읽고 $빈칸을 채운다. 없는 빈칸은 그대로 둔다(safe_substitute)."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).safe_substitute(fields)


def build_subagents(tools: dict[str, BaseTool], ledger: RunLedger, ports: AgentPorts) -> list[dict]:
    """서브에이전트 spec 목록. 모델은 명시하지 않아 메인의 것을 물려받는다."""
    fields = {"language": ports.language, "framework": ports.framework, "style": ports.style_notes}
    specs = []
    for name, tool_names in SUBAGENT_TOOLS.items():
        prompt = (
            load_prompt(name, **fields)
            if name != GENERAL_PURPOSE
            else "이 에이전트는 쓰지 않는다. 받은 요청을 수행하지 말고 "
            "'explorer / writer / diagnoser 중 하나를 써라'라고만 답하라."
        )
        specs.append(
            {
                "name": name,
                "description": _DESCRIPTIONS[name],
                "system_prompt": prompt,
                "tools": [tools[n] for n in tool_names],
                # 원장·쓰기 도구 숨김·녹음/재생·토큰 합산 — 메인과 같은 인스턴스(한 실행 = 하나)
                "middleware": [ledger, HideWriteTools(), *ports.llm_middleware],
            }
        )
    return specs
