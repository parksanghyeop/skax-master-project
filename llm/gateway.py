"""사내 LLM 게이트웨이 HTTP 클라이언트.

OpenAI 호환 chat completions 형식을 가정한다(사내 게이트웨이 스펙 미확정 —
poc-findings 1주차 확인 목록. 확정되면 이 파일만 고치면 된다).
층: llm. 서버 주소·API 토큰은 환경변수로만 받는다(v4 6.6 — 코드·설정 파일 기록 금지).
"""

import json
import os
import urllib.request
from urllib.error import URLError

from llm.client import ChatMessage, ChatResponse

# 환경변수 이름. 값이 아니라 이름만 코드에 둔다(v4 6.6).
ENV_BASE_URL = "CTA_GATEWAY_URL"
ENV_API_TOKEN = "CTA_GATEWAY_TOKEN"

# 게이트웨이 무응답으로 파이프라인이 잠기지 않게 하는 상한. 임시값(스펙 확정 시 조정).
REQUEST_TIMEOUT_SECONDS = 120


class GatewayConfigError(RuntimeError):
    """필수 환경변수가 없을 때 — 시크릿을 코드·파일로 받지 않으므로 대안은 없다."""


class GatewayCallError(RuntimeError):
    """게이트웨이 호출 실패(네트워크·비정상 응답). 원인 요약을 메시지에 담는다."""


def build_payload(messages: list[ChatMessage], model: str) -> dict:
    """chat completions 요청 본문을 만든다 (OpenAI 호환 형식).

    순수 함수로 분리한 이유: 네트워크 없이 요청 형식을 단위 테스트하기 위해서.
    """
    return {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }


class GatewayClient:
    """게이트웨이에 chat 요청을 보내는 실호출 클라이언트 (LlmClient 구현).

    실패 시 동작: 환경변수 없음 → GatewayConfigError(생성 시점),
    호출 실패·응답 형식 이상 → GatewayCallError.
    """

    def __init__(self) -> None:
        base_url = os.environ.get(ENV_BASE_URL)
        token = os.environ.get(ENV_API_TOKEN)
        if not base_url or not token:
            raise GatewayConfigError(
                f"환경변수 {ENV_BASE_URL}·{ENV_API_TOKEN}가 필요하다 — "
                "시크릿은 환경변수로만(v4 6.6)"
            )
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._token = token

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        body = json.dumps(build_payload(messages, model)).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            # 토큰이 오류 문구에 섞여 나가지 않도록 원인만 요약한다(시크릿 가림, v4 6.6)
            raise GatewayCallError(f"게이트웨이 호출 실패: {e.reason}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise GatewayCallError(f"응답 형식 이상: 최상위 키 {sorted(data)[:10]}") from e
        return ChatResponse(content=content)
