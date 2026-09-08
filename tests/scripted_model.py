"""테스트용 대본 채팅 모델 — Deep Agents·미들웨어를 LLM 없이 돌린다.

준비된 AIMessage를 호출 순서대로 돌려준다. 입력을 보지 않으므로 대본 순서가 곧 시나리오다.
bind_tools는 자기 자신을 돌려줘 에이전트 조립(도구 바인딩)을 통과한다.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def ai(content: str = "", tool_calls: list[dict] | None = None, tokens: int = 0) -> AIMessage:
    """대본 항목 하나. tool_calls: [{"name", "args", "id"}]. tokens는 usage_metadata에 들어간다."""
    usage = None
    if tokens:
        usage = {"input_tokens": tokens - 1, "output_tokens": 1, "total_tokens": tokens}
    return AIMessage(content=content, tool_calls=tool_calls or [], usage_metadata=usage)


class ScriptedChatModel(BaseChatModel):
    """준비된 응답을 차례로 돌려주는 모델. 대본이 소진되면 AssertionError."""

    script: list[AIMessage] = []
    cursor: int = 0
    deployment_name: str = "scripted"
    calls: list[list[BaseMessage]] = []  # 호출마다 받은 메시지 — 프롬프트 내용 검증용

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        self.calls.append(list(messages))
        if self.cursor >= len(self.script):
            raise AssertionError(f"대본 소진: {len(self.script)}개를 넘어 호출됐다")
        message = self.script[self.cursor]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])
