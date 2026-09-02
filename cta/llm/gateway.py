"""사내 LLM 게이트웨이 HTTP 클라이언트 — Azure OpenAI 호환 형식 (ADR-0011).

경로가 `/openai/deployments/{deployment}/chat/completions`이고 deployment 이름이
곧 모델 선택이다 — LlmClient.chat의 model 인자를 deployment 이름으로 쓴다.
층: llm. 서버 주소·API 키는 환경변수/.env로만 받는다(v4 6.6 — 리포 기록 금지).
"""

import json
import os
import urllib.request
from urllib.error import URLError

from cta.llm.client import ChatMessage, ChatResponse

# 환경변수 이름. 값(주소·키)은 코드에 절대 넣지 않는다(v4 6.6).
ENV_BASE_URL = "CTA_GATEWAY_URL"
ENV_API_KEY = "CTA_GATEWAY_API_KEY"
ENV_API_VERSION = "CTA_GATEWAY_API_VERSION"  # 생략 시 기본값 사용

# API 버전은 스펙 문자열이라 비밀이 아니다 — 게이트웨이 안내 기준(2026-09 확인).
DEFAULT_API_VERSION = "2024-12-01-preview"

# 게이트웨이 무응답으로 파이프라인이 잠기지 않게 하는 상한. gpt-5가 메서드 4개짜리 테스트
# 파일을 만드는 데 120초를 넘긴 실측(2026-09-03)이 있어 300초로 올렸다. 조정: CTA_GATEWAY_TIMEOUT
REQUEST_TIMEOUT_SECONDS = 300
ENV_TIMEOUT = "CTA_GATEWAY_TIMEOUT"


class GatewayConfigError(RuntimeError):
    """필수 환경변수가 없을 때 — 시크릿을 코드·파일로 받지 않으므로 대안은 없다."""


class GatewayCallError(RuntimeError):
    """게이트웨이 호출 실패(네트워크·비정상 응답). 원인 요약을 메시지에 담는다."""


def build_url(base_url: str, deployment: str, api_version: str) -> str:
    """chat completions 요청 URL을 만든다 (Azure OpenAI 호환 경로).

    순수 함수로 분리한 이유: 네트워크 없이 경로 규칙을 단위 테스트하기 위해서.
    """
    return (
        f"{base_url.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )


def build_payload(messages: list[ChatMessage]) -> dict:
    """요청 본문을 만든다. 모델 선택은 본문이 아니라 URL(deployment)이 담당한다."""
    return {"messages": [{"role": m.role, "content": m.content} for m in messages]}


class GatewayClient:
    """게이트웨이에 chat 요청을 보내는 실호출 클라이언트 (LlmClient 구현).

    실패 시 동작: 환경변수 없음 → GatewayConfigError(생성 시점),
    호출 실패·응답 형식 이상 → GatewayCallError.
    """

    def __init__(self) -> None:
        base_url = os.environ.get(ENV_BASE_URL)
        api_key = os.environ.get(ENV_API_KEY)
        if not base_url or not api_key:
            raise GatewayConfigError(
                f"환경변수 {ENV_BASE_URL}·{ENV_API_KEY}가 필요하다 — "
                ".env(gitignore) 또는 환경변수로만 설정한다(v4 6.6, ADR-0011)"
            )
        self._base_url = base_url
        self._api_key = api_key
        self._api_version = os.environ.get(ENV_API_VERSION) or DEFAULT_API_VERSION
        try:
            self._timeout = int(os.environ.get(ENV_TIMEOUT, "") or REQUEST_TIMEOUT_SECONDS)
        except ValueError:
            self._timeout = REQUEST_TIMEOUT_SECONDS

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        body = json.dumps(build_payload(messages)).encode("utf-8")
        request = urllib.request.Request(
            build_url(self._base_url, model, self._api_version),
            data=body,
            headers={
                "Content-Type": "application/json",
                # 게이트웨이는 api-key 헤더와 Bearer 둘 다 받는다 — 단순한 쪽을 쓴다
                "api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            # 키가 오류 문구에 섞여 나가지 않도록 원인만 요약한다(시크릿 가림, v4 6.6)
            raise GatewayCallError(f"게이트웨이 호출 실패 (deployment={model}): {e.reason}") from e
        except (TimeoutError, OSError) as e:
            # 응답 읽기 도중 시간 초과는 URLError가 아니라 소켓 예외로 온다
            raise GatewayCallError(
                f"게이트웨이 응답 대기 초과 (deployment={model}, {self._timeout}초): {e} — "
                f"{ENV_TIMEOUT}로 상한을 늘릴 수 있다"
            ) from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise GatewayCallError(f"응답 형식 이상: 최상위 키 {sorted(data)[:10]}") from e
        # usage는 선택 항목 — 없어도 응답은 유효하다(토큰 수만 0으로 남는다)
        usage = data.get("usage") or {}
        try:
            tokens = int(usage.get("total_tokens", 0))
        except (TypeError, ValueError):
            tokens = 0
        return ChatResponse(content=content or "", usage_tokens=tokens)
