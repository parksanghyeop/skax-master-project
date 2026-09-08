"""사람 개입 장치 — LangGraph interrupt로 사용자에게 묻고, 답을 받아 같은 지점부터 재개한다.

v4 2.3의 ⏸ 멈춤 지점. 옛 작성 그래프(writer_graph)와 Deep Agent(core/agent)가 같은 장치를 쓴다 —
어느 쪽이든 checkpointer가 있는 그래프 안에서 `interrupt()`가 실행을 멈추고, 호출부가 답을 넣어
재개한다(ADR-0012 결정 2, ADR-0024). 층: core — 언어·LLM을 모른다.
"""

from collections.abc import Callable
from typing import Any

from langgraph.types import Command, interrupt

from cta.core.ports import UserReply


class InterruptUserGate:
    """LangGraph interrupt로 실제 사용자에게 묻는 UserGate 구현.

    ask가 호출되는 순간 그래프가 그 자리에서 **정지**하고 상태가 저장된다.
    invoke_with_interrupts(아래)가 질문을 밖으로 전달하고, 사용자의 답으로
    같은 지점부터 재개한다 — 답이 늦게 와도 손실이 없다(v4 2.3).
    checkpointer가 있는 그래프 안에서만 동작한다.
    """

    def ask(self, question: str) -> UserReply:
        payload = interrupt({"question": question})
        # 재개 시 interrupt()가 사용자의 답(payload)을 그대로 돌려준다
        return UserReply(
            action=str(payload.get("action", "continue")),
            hint=str(payload.get("hint", "")),
        )


def invoke_with_interrupts(
    app: Any,
    initial_state: dict,
    thread_id: str,
    ask_user: Callable[[str], UserReply],
    recursion_limit: int | None = None,
) -> dict:
    """그래프를 실행하되, 중단(interrupt)이 오면 ask_user로 답을 받아 재개한다.

    입력: app — checkpointer와 함께 컴파일된 그래프, thread_id — 재개용 식별자,
      ask_user — 질문 문자열을 받아 UserReply를 돌려주는 콜백(CLI는 stdin 입력),
      recursion_limit — 그래프 단계 수 상한(도구 호출형 에이전트는 기본 25로는 모자란다).
    출력: 최종 상태. 중단이 없으면 한 번의 invoke와 같다.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    result = app.invoke(initial_state, config)
    while "__interrupt__" in result:
        question = result["__interrupt__"][0].value["question"]
        reply = ask_user(question)
        result = app.invoke(Command(resume={"action": reply.action, "hint": reply.hint}), config)
    return result
