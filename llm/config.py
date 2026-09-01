"""LLM 클라이언트 생성의 유일한 입구 — 사내 게이트웨이 직결 (ADR-0011).

설정 우선순위: 환경변수 > `.env` 파일(리포 루트). `.env`는 gitignore 대상이라
서버 주소·API 키가 원격 레포에 올라가는 경로가 없다(v4 6.6). 커밋되는 것은
키 이름만 적은 `.env.example`뿐이다. 백엔드 스펙이 바뀌면 이 모듈만 고친다.
층: llm.
"""

import os
from pathlib import Path

from llm.client import LlmClient

# 설정 키 이름. 값은 코드에 절대 넣지 않는다.
ENV_MODEL = "CTA_LLM_MODEL"  # 게이트웨이 deployment 이름. 미설정 시 기본값

# 기본 deployment. 게이트웨이 제공 목록(gpt-4.1/4.1-mini/4o/4o-mini/5/5-mini/5.4/5.6-luna)
# 중 보수적 선택 — 모델 비교 실험은 2단계 평가 하네스에서 한다.
DEFAULT_MODEL = "gpt-4.1"

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

    왜 필요한가: GatewayClient는 os.environ만 읽는다 — .env를 여기서 주입해야
    "파일 하나로 전체 설정"이 성립한다.
    """
    for key, value in read_dotenv(path).items():
        os.environ.setdefault(key, value)


def make_llm_client() -> tuple[LlmClient, str]:
    """(게이트웨이 클라이언트, deployment 이름)을 만든다.

    실패 시 동작: 주소·키 미설정은 GatewayClient가 GatewayConfigError로 알린다.
    """
    load_dotenv_into_env()
    from llm.gateway import GatewayClient

    model = os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL
    return GatewayClient(), model
