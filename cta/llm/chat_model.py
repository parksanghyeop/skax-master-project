"""LangChain 모델 생성 — Deep Agents 경로의 게이트웨이 접속 (ADR-0024 결정 5).

`gateway.py`(urllib 직결)와 같은 환경변수·같은 URL 규칙(ADR-0011)으로 `AzureChatOpenAI`를
만든다. 에이전트는 이 모델 객체만 받고, 실제 호출은 `model_cassette.py` 미들웨어가
녹음·재생한다. 재생 모드에는 호출 자체가 불가능한 `NoCallChatModel`을 넣는다 — 실호출
폴백이 구조적으로 없다(R7). 층: llm — 모델 생성의 유일한 입구는 `make_chat_model`이다.
"""

import os
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from cta.llm.config import DEFAULT_MODEL, ENV_MODEL, load_dotenv_into_env
from cta.llm.gateway import (
    DEFAULT_API_VERSION,
    ENV_API_KEY,
    ENV_API_VERSION,
    ENV_BASE_URL,
    ENV_REASONING_EFFORT,
    ENV_TIMEOUT,
    REASONING_EFFORT_DEFAULT,
    REQUEST_TIMEOUT_SECONDS,
    GatewayConfigError,
    is_reasoning_model,
)


def make_chat_model(
    dotenv_path: str | Path | None = None,
    *,
    model: str | None = None,
    model_default: str | None = None,
    timeout_default: int | None = None,
    reasoning_effort_default: str | None = None,
) -> tuple[BaseChatModel, str]:
    """(LangChain 채팅 모델, deployment 이름)을 만든다.

    model: 이번 실행만 쓸 deployment(`--model`) — 모든 설정보다 앞선다. deployment가 모델 객체에
      박히므로 옛 클라이언트처럼 호출 시점에 바꿀 수 없어 생성 인자로 받는다.
    나머지 우선순위는 `make_llm_client`와 같다: 환경변수 > .env > cta.toml(`*_default`) >
    코드 기본값.
    `*_default`는 환경변수에 써넣지 않는다(오래 사는 프로세스 오염 방지).
    실패 시 동작: 주소·키가 없으면 GatewayConfigError — 메시지에 키 값은 넣지 않는다.
    """
    load_dotenv_into_env(dotenv_path)
    base_url = os.environ.get(ENV_BASE_URL, "").strip()
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    if not base_url or not api_key:
        raise GatewayConfigError(
            f"환경변수 {ENV_BASE_URL}·{ENV_API_KEY}가 필요하다 — "
            ".env 또는 환경변수로만 전달한다(ADR-0011)"
        )
    model = (
        (model or "").strip()
        or os.environ.get(ENV_MODEL, "").strip()
        or (model_default or "").strip()
        or DEFAULT_MODEL
    )
    effort = (
        os.environ.get(ENV_REASONING_EFFORT, "").strip()
        or (reasoning_effort_default or "").strip()
        or REASONING_EFFORT_DEFAULT
    )
    timeout = int(
        os.environ.get(ENV_TIMEOUT, "").strip() or timeout_default or REQUEST_TIMEOUT_SECONDS
    )

    # langchain-openai는 무거운 의존성이라 함수 안에서 import — 재생 모드·단위 테스트는 필요 없다
    from langchain_openai import AzureChatOpenAI

    kwargs: dict[str, Any] = {
        "azure_endpoint": base_url,
        "azure_deployment": model,
        "api_version": os.environ.get(ENV_API_VERSION, "").strip() or DEFAULT_API_VERSION,
        "api_key": api_key,
        "timeout": timeout,
    }
    # 추론 강도는 추론 모델에만 보낸다 — 비추론 모델은 400으로 거부한다(ADR-0023)
    if effort.lower() != "none" and is_reasoning_model(model):
        kwargs["reasoning_effort"] = effort
    return AzureChatOpenAI(**kwargs), model


class NoCallChatModel(BaseChatModel):
    """호출하면 예외를 던지는 모델 — 재생 모드 전용 자리 채우기.

    Deep Agents는 모델 객체를 요구하지만 재생 모드에서는 카세트 미들웨어가 모든 호출을
    가로채므로 실제 모델이 필요 없다. 미들웨어를 비켜 간 호출(예: 요약 미들웨어의 직접 호출)이
    있으면 조용히 실호출로 가는 대신 여기서 실패한다 — 재생은 폴백하지 않는다(R7).
    """

    deployment_name: str = "replay"

    @property
    def _llm_type(self) -> str:
        return "no-call"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "NoCallChatModel":
        # 도구 스키마는 재생에 필요 없다 — 자기 자신을 돌려주면 에이전트 조립이 그대로 된다
        return self

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        raise RuntimeError(
            "재생 모드에서 모델 실호출이 시도됐다 — 카세트 미들웨어를 비켜 간 호출이다. "
            "요약 미들웨어가 발동했다면 기록을 다시 만든다(R7: 실호출 폴백 없음)"
        )
