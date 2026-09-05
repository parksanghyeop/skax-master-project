"""토큰 사용량 합산 — 어떤 LlmClient든 감싸서 호출 수·토큰을 센다.

왜 별도 래퍼인가: 게이트웨이·재생 클라이언트 어느 쪽이든 같은 방법으로 세야
"소요 … 토큰" 출력(시나리오 SC-001)이 실호출·재생 모두에서 나온다. 층: llm.
"""

from cta.llm.client import ChatMessage, ChatResponse, LlmClient


class BudgetExceededError(RuntimeError):
    """한 번의 실행이 토큰 예산(cta.toml [budget] max_tokens_per_run)을 넘었다.

    왜 예외인가: 예산은 "여기서 멈춘다"는 약속이다. 조용히 계속 호출하면 예산이 아니다.
    호출부(cli)는 이 예외를 받아 생성물을 되돌리고 안내 문구를 낸다.
    """


class MeteredClient:
    """inner 클라이언트에 위임하면서 호출 수와 usage_tokens 합계를 기록한다.

    max_tokens: 누적 토큰이 이 값에 닿으면 다음 호출을 하지 않고 BudgetExceededError.
      None이면 무제한(기본). 검사는 호출 **전**에 한다 — 이미 넘은 상태에서 한 번 더 부르지 않는다.
    """

    def __init__(self, inner: LlmClient, max_tokens: int | None = None) -> None:
        self._inner = inner
        self._max_tokens = max_tokens
        self.calls = 0
        self.total_tokens = 0

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        if self._max_tokens is not None and self.total_tokens >= self._max_tokens:
            raise BudgetExceededError(
                f"토큰 예산 초과: 누적 {self.total_tokens:,} / 상한 {self._max_tokens:,} "
                f"(호출 {self.calls}회) — cta.toml [budget] max_tokens_per_run"
            )
        response = self._inner.chat(messages, model)
        self.calls += 1
        self.total_tokens += int(response.usage_tokens or 0)
        return response
