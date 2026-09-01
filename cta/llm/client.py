"""LLM 호출의 공용 타입과 클라이언트 인터페이스.

모든 LLM 호출은 llm/ 계층의 이 인터페이스를 거친다(절대 규칙 R7) — 그래야
record & replay(replay.py)가 실제 게이트웨이(gateway.py)와 똑같은 자리에
끼워질 수 있다. 층: llm.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    """대화 메시지 한 건. role: "system" | "user" | "assistant"."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatResponse:
    """모델 응답. PoC에서는 텍스트만 쓴다 — tool calling 지원 여부가 확정되면
    (1주차 확인 3번) 필드를 늘린다."""

    content: str


class LlmClient(Protocol):
    """chat 한 번을 수행하는 클라이언트.

    입력: messages 대화 이력, model 게이트웨이 모델 이름.
    출력: ChatResponse.
    실패 시 동작: 구현별 예외 — 게이트웨이 오류(gateway), 카세트 없음(replay).
    """

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse: ...
