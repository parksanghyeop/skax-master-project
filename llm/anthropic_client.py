"""Anthropic Claude API 클라이언트 — 개발 환경의 실호출 백엔드 (ADR-0010).

공식 anthropic SDK를 쓴다: 인증 자동 해석(ANTHROPIC_API_KEY 환경변수 →
`ant auth login` 프로필), 429/5xx 재시도, 타입 예외가 내장돼 있다.
층: llm — 모든 호출은 LlmClient 포트 뒤에서 일어난다(R7). 시크릿은
환경변수/.env로만 받고 코드·카세트에 남기지 않는다(v4 6.6).
"""

from llm.client import ChatMessage, ChatResponse

# 비스트리밍 요청의 안전 상한 (claude-api 스킬 권장 기본값).
DEFAULT_MAX_TOKENS = 16000

# 서버측 fallback을 켤 모델 접두사 — 이 계열은 안전 분류기가 요청을 거절할 수 있어
# 권장 대체 모델로 자동 재시도하게 한다(claude-api 스킬 권장).
_FALLBACK_MODEL_PREFIXES = ("claude-opus-5", "claude-fable-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeRefusalError(RuntimeError):
    """안전 분류기가 요청을 거절함(stop_reason=refusal). 같은 프롬프트 재시도 금지."""


class ClaudeClient:
    """Claude Messages API로 chat 한 번을 수행한다 (LlmClient 구현).

    실패 시 동작: 자격 증명 부재·네트워크 오류는 anthropic SDK 예외 그대로,
      안전 거절은 ClaudeRefusalError로 구분해 던진다(폴백 체인까지 거절한 경우).
    """

    def __init__(self) -> None:
        import anthropic  # 지연 import — config가 gateway를 고르면 SDK가 없어도 된다

        # 인자 없는 생성: SDK가 환경(.env는 config가 주입)에서 자격 증명을 해석한다
        self._client = anthropic.Anthropic()

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        system_text, api_messages = split_messages(messages)
        kwargs: dict = {
            "model": model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": api_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if model.startswith(_FALLBACK_MODEL_PREFIXES):
            response = self._client.beta.messages.create(
                betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
            )
        else:
            response = self._client.messages.create(**kwargs)

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise ClaudeRefusalError(f"안전 거절: {detail} — 같은 프롬프트로 재시도하지 말 것")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return ChatResponse(content=text)


def split_messages(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    """공용 ChatMessage 목록을 Anthropic 형식(system 파라미터 + messages)으로 나눈다.

    순수 함수로 분리한 이유: 네트워크 없이 변환 규칙을 단위 테스트하기 위해서.
    """
    system_parts = [m.content for m in messages if m.role == "system"]
    api_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return "\n\n".join(system_parts), api_messages
