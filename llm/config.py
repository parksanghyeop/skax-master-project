"""LLM 백엔드 선택 설정 — 개발(Claude API) ↔ 운영(사내 게이트웨이) 전환 지점 (ADR-0010).

설정 우선순위: 환경변수 > `.env` 파일(리포 루트). `.env`는 gitignore 대상이라
시크릿이 원격 레포에 올라가는 경로가 없다(v4 6.6). 커밋되는 것은 키 이름만 적은
`.env.example`뿐이다. 층: llm — 클라이언트 생성은 반드시 make_llm_client를 경유한다.
"""

import os
from pathlib import Path

from llm.client import LlmClient

# 설정 키 이름. 값은 코드에 절대 넣지 않는다.
ENV_PROVIDER = "CTA_LLM_PROVIDER"  # "claude"(개발 기본) | "gateway"(운영)
ENV_MODEL = "CTA_LLM_MODEL"  # 미설정 시 provider별 기본값

PROVIDER_CLAUDE = "claude"
PROVIDER_GATEWAY = "gateway"

DEFAULT_MODELS = {
    # claude-api 스킬 기준 권장 기본 모델 (2026-09 확인)
    PROVIDER_CLAUDE: "claude-opus-5",
    # 게이트웨이 모델 이름은 사내 스펙 확정 후 갱신 — poc-findings 확인 목록 참조
    PROVIDER_GATEWAY: "qwen",
}

_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class LlmConfigError(RuntimeError):
    """설정이 없거나 모순일 때 — 무엇을 어떻게 채워야 하는지 메시지에 담는다."""


def read_dotenv(path: str | Path) -> dict[str, str]:
    """KEY=VALUE 형식의 .env 파일을 읽는다. 주석(#)·빈 줄 무시, 값의 '='는 보존.

    왜 직접 파싱하나: python-dotenv 의존성 하나를 아끼는 정도의 단순한 형식이다.
    """
    result: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return result
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def load_dotenv_into_env(path: str | Path = _DOTENV_PATH) -> None:
    """.env 내용을 환경변수로 주입한다. 이미 설정된 환경변수가 항상 이긴다.

    왜 필요한가: anthropic SDK·GatewayClient는 os.environ만 읽는다 —
    .env를 여기서 주입해야 "파일 하나로 전 백엔드 설정"이 성립한다.
    """
    for key, value in read_dotenv(path).items():
        os.environ.setdefault(key, value)


def make_llm_client() -> tuple[LlmClient, str]:
    """설정에 따라 (클라이언트, 기본 모델 이름)을 만든다.

    실패 시 동작: 모르는 provider → LlmConfigError.
      자격 증명 부재는 각 클라이언트가 첫 사용 시점에 자체 예외로 알린다.
    """
    load_dotenv_into_env()
    provider = os.environ.get(ENV_PROVIDER, PROVIDER_CLAUDE).strip().lower()
    model = os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODELS.get(provider, "")

    if provider == PROVIDER_CLAUDE:
        # 지연 import: 게이트웨이만 쓰는 환경에서 anthropic SDK를 요구하지 않기 위해
        from llm.anthropic_client import ClaudeClient

        return ClaudeClient(), model
    if provider == PROVIDER_GATEWAY:
        from llm.gateway import GatewayClient

        return GatewayClient(), model
    raise LlmConfigError(
        f"{ENV_PROVIDER}={provider!r}는 모르는 값이다 — "
        f"{PROVIDER_CLAUDE!r} 또는 {PROVIDER_GATEWAY!r} 중 하나를 쓰라 (.env 또는 환경변수)"
    )
