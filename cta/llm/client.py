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
    """모델 응답 텍스트 + 사용 토큰 수.

    usage_tokens: 게이트웨이가 알려준 총 토큰(입력+출력). 모르면 0 — 재생 기록에
    값이 없던 시절의 호환용 기본값. 소요 비용을 시나리오 출력("34,200 토큰")에
    보여주기 위해 둔다(ADR-0015 D6).
    """

    content: str
    usage_tokens: int = 0


class LlmClient(Protocol):
    """chat 한 번을 수행하는 클라이언트.

    입력: messages 대화 이력, model 게이트웨이 모델 이름.
    출력: ChatResponse.
    실패 시 동작: 구현별 예외 — 게이트웨이 오류(gateway), 카세트 없음(replay).
    """

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse: ...
