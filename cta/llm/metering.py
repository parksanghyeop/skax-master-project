"""토큰 사용량 합산 — 어떤 LlmClient든 감싸서 호출 수·토큰을 센다.

왜 별도 래퍼인가: 게이트웨이·재생 클라이언트 어느 쪽이든 같은 방법으로 세야
"소요 … 토큰" 출력(시나리오 SC-001)이 실호출·재생 모두에서 나온다. 층: llm.
"""

from cta.llm.client import ChatMessage, ChatResponse, LlmClient


class MeteredClient:
    """inner 클라이언트에 위임하면서 호출 수와 usage_tokens 합계를 기록한다."""

    def __init__(self, inner: LlmClient) -> None:
        self._inner = inner
        self.calls = 0
        self.total_tokens = 0

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        response = self._inner.chat(messages, model)
        self.calls += 1
        self.total_tokens += int(response.usage_tokens or 0)
        return response
