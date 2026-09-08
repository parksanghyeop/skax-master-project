"""토큰 사용량 합산 — 옛 클라이언트(MeteredClient)와 Deep Agents 경로(MeteringModelMiddleware).

왜 별도 래퍼인가: 게이트웨이·재생 어느 쪽이든 같은 방법으로 세야 "소요 … 토큰" 출력(시나리오
SC-001)이 실호출·재생 모두에서 나온다. 두 판은 같은 숫자(calls·total_tokens·breakdown)를 낸다.
층: llm.
"""

from langchain.agents.middleware import AgentMiddleware

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
        # 내역(ADR-0023) — 재생 기록에는 없어 0으로 남을 수 있다
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        if self._max_tokens is not None and self.total_tokens >= self._max_tokens:
            raise BudgetExceededError(
                f"토큰 예산 초과: 누적 {self.total_tokens:,} / 상한 {self._max_tokens:,} "
                f"(호출 {self.calls}회) — cta.toml [budget] max_tokens_per_run"
            )
        response = self._inner.chat(messages, model)
        self.calls += 1
        self.total_tokens += int(response.usage_tokens or 0)
        self.prompt_tokens += int(response.prompt_tokens or 0)
        self.completion_tokens += int(response.completion_tokens or 0)
        self.reasoning_tokens += int(response.reasoning_tokens or 0)
        self.cached_tokens += int(response.cached_tokens or 0)
        return response

    def breakdown(self) -> dict[str, int]:
        """화면·결과 dict용 토큰 내역."""
        return {
            "total": self.total_tokens,
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "reasoning": self.reasoning_tokens,
            "cached": self.cached_tokens,
        }


class MeteringModelMiddleware(AgentMiddleware):
    """LangChain 모델 호출 미들웨어판 — Deep Agents 경로의 호출 수·토큰 합산 (ADR-0024).

    usage는 AIMessage.usage_metadata에서 읽는다 — 재생 기록에도 들어 있어 재생 시에도 합산된다.
    미들웨어 목록에서 **카세트 미들웨어보다 앞**에 둔다(바깥쪽) — 재생은 handler를 부르지 않으므로
    뒤에 두면 재생 호출을 세지 못한다. 예산 검사는 MeteredClient처럼 호출 **전**이다.
    """

    name = "cta_model_metering"

    def __init__(self, max_tokens: int | None = None) -> None:
        super().__init__()
        self._max_tokens = max_tokens
        self.calls = 0
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0

    def breakdown(self) -> dict[str, int]:
        """화면·결과 dict용 토큰 내역 — MeteredClient.breakdown과 같은 모양."""
        return {
            "total": self.total_tokens,
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "reasoning": self.reasoning_tokens,
            "cached": self.cached_tokens,
        }

    def wrap_model_call(self, request, handler):
        if self._max_tokens is not None and self.total_tokens >= self._max_tokens:
            raise BudgetExceededError(
                f"토큰 예산 초과: 누적 {self.total_tokens:,} / 상한 {self._max_tokens:,} "
                f"(호출 {self.calls}회) — cta.toml [budget] max_tokens_per_run"
            )
        response = handler(request)
        self.calls += 1
        # handler 반환은 ModelResponse(result 목록) 또는 AIMessage 하나
        messages = [response] if hasattr(response, "usage_metadata") else list(response.result)
        for message in messages:
            usage = getattr(message, "usage_metadata", None) or {}
            self.total_tokens += int(usage.get("total_tokens") or 0)
            self.prompt_tokens += int(usage.get("input_tokens") or 0)
            self.completion_tokens += int(usage.get("output_tokens") or 0)
            details_out = usage.get("output_token_details") or {}
            details_in = usage.get("input_token_details") or {}
            self.reasoning_tokens += int(details_out.get("reasoning") or 0)
            self.cached_tokens += int(details_in.get("cache_read") or 0)
        return response
