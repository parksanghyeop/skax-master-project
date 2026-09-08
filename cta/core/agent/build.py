"""Deep Agent 조립과 실행 — 메인 test-lead + 서브 3 (ADR-0024).

`build_agent`가 create_deep_agent를 한 번 호출해 앱을 만들고, `run_agent`가 작업 지침서·재료로
실행한 뒤 결과를 옛 작성 그래프와 같은 모양(WriterState 키)으로 돌려준다 — 게이트 루프
(core/submit.py)와 화면 출력이 두 엔진에서 같은 코드를 쓰기 위해서다.
층: core — 포트·모델 객체만 안다. backend 루트·테스트 경로는 호출부가 준다(R1).
"""

from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware

from cta.core.agent.limits import (
    ASK_EVERY_ATTEMPTS,
    MAX_TOTAL_ATTEMPTS,
    PASSED_PREFIX,
    HideWriteTools,
    RunLedger,
)
from cta.core.agent.ports import AgentPorts
from cta.core.agent.subagents import build_subagents, load_prompt
from cta.core.agent.tools import ASK_USER_TOOL, make_tools
from cta.core.tools import check_quality
from cta.core.user_gate import invoke_with_interrupts

# 메인이 직접 갖는 도구 — 위임(task)·계획(write_todos)은 하네스가 더한다(ADR-0025).
MAIN_TOOLS = ("check_quality", "report_finding", ASK_USER_TOOL)

# 그래프 단계 상한. 도구 호출 1회 = 단계 2개, 위임 1회는 서브의 단계까지 포함한다.
# 시도 8회 × (쓰기+실행) × 위임 왕복에 여유를 둔 값 — 무한 반복은 원장(RunLedger)이 막는다.
RECURSION_LIMIT = 400


def build_agent(
    ports: AgentPorts,
    *,
    ask_every: int = ASK_EVERY_ATTEMPTS,
    max_total: int = MAX_TOTAL_ATTEMPTS,
    checkpointer: Any = None,
) -> tuple[Any, RunLedger]:
    """(컴파일된 Deep Agent, 원장)을 만든다. 실행 한 번마다 새로 만든다(원장의 시도 수는 실행 단위).

    checkpointer: ask_user(interrupt)를 쓰려면 필수. 없으면 대본 게이트 전용(테스트).
    """
    tools = make_tools(ports)
    ledger = RunLedger(ask_every, max_total, progress=ports.progress)
    app = create_deep_agent(
        model=ports.model,
        tools=[tools[name] for name in MAIN_TOOLS],
        system_prompt=load_prompt("test_lead", language=ports.language),
        middleware=[TodoListMiddleware(), HideWriteTools(), ledger, *ports.llm_middleware],
        subagents=build_subagents(tools, ledger, ports),
        # 내장 쓰기 도구는 전 경로 거부 — 파일을 바꾸는 길은 write_test뿐(ADR-0025 결정 2)
        permissions=[FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")],
        backend=FilesystemBackend(root_dir=ports.project_root, virtual_mode=True),
        checkpointer=checkpointer,
    )
    return app, ledger


def task_text(instruction: str, context: str, target: str, test_path: str, selector: str) -> str:
    """메인에게 주는 첫 메시지 — 지침서·재료·고정 값. 고정 값은 서브에게 그대로 전달된다."""
    return (
        f"[작업 지침서]\n{instruction}\n\n"
        f"[재료]\n{context or '(없음)'}\n\n"
        "[고정 값 — 서브에이전트에게 그대로 전달한다]\n"
        f"대상: {target}\n"
        f"테스트 파일 경로(write_test의 path, check_quality의 path): {test_path}\n"
        f"실행 selector(run_tests의 selector): {selector}"
    )


def run_agent(
    app: Any,
    ledger: RunLedger,
    ports: AgentPorts,
    *,
    instruction: str,
    context: str,
    target: str,
    test_path: str,
    selector: str,
    thread_id: str,
    ask_user: Any,
) -> dict:
    """에이전트를 끝까지 돌리고 WriterState 모양의 dict를 돌려준다.

    status는 결정적으로 정한다(R2): report_finding이 불렸거나 마지막 실행이 통과가 아니면
    "reported", 아니면 "passed". 통과인데 메인이 check_quality를 안 불렀으면 하네스가 직접
    부른다 — 품질 확인은 판단이 아니라 측정이다.
    """
    invoke_with_interrupts(
        app,
        {
            "messages": [
                {
                    "role": "user",
                    "content": task_text(instruction, context, target, test_path, selector),
                }
            ]
        },
        thread_id=thread_id,
        ask_user=ask_user,
        recursion_limit=RECURSION_LIMIT,
    )
    passed = ledger.last_run.startswith(PASSED_PREFIX) and not ledger.report
    quality = ledger.quality
    if passed and not quality:
        quality = check_quality(ports.checker, test_path)
    report = ledger.report
    if not passed and not report:
        report = (
            f"대상 {target}의 테스트를 통과시키지 못했다 "
            f"(시도 {ledger.attempts}회, 한계 보고 없이 종료).\n"
            f"마지막 실패:\n{ledger.last_run or '(실행 없음)'}"
        )
    return {
        "instruction": instruction,
        "target": target,
        "test_path": test_path,
        "selector": selector,
        "context": context,
        "test_code": ledger.last_code,
        "write_result": ledger.last_write_result,
        "last_run": ledger.last_run,
        "prev_run": ledger.prev_run,
        "attempts": ledger.attempts,
        "quality": quality,
        "report": report,
        "status": "passed" if passed else "reported",
        "extra_context": context,
        "history": list(ledger.history),
    }
