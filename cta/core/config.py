"""cta.toml 설정 읽기 — 게이트 기준치·반복 상한·게이트웨이 시간 초과·모델·토큰 예산을 한 파일에서.

3단계 스킬 "설정 파일: 커버리지 기준치, 재시도 상한, 반복·비용 예산, 모델 선택. 기본값은 v4와 일치".
왜 core에 있나: 키 이름과 기본값은 언어와 무관한 공통 관심사다(R1 — 대상 언어 이름이 없다).
시크릿(게이트웨이 주소·API 키)은 이 파일로 받지 않는다 — .env·환경변수만(ADR-0011).

우선순위(높은 쪽이 이긴다): 환경변수 > .env > cta.toml > 코드 기본값.
cta.toml 값은 cli가 `make_llm_client(model_default=…, timeout_default=…)`로 넘기고, 환경변수·.env에
값이 없을 때만 쓰인다. 환경변수에 써넣지 않는다(오래 사는 프로세스가 프로젝트를 바꿔도 오염 없음).

형식 예 (대상 프로젝트 루트의 cta.toml):
    [gates]
    line_min = 0.9
    [retry]
    ask_every = 4
    max_total = 8
    [gateway]
    timeout_sec = 600
    [llm]
    model = "gpt-5"
    [budget]
    max_tokens_per_run = 50000
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from cta.core.gates import CONFIG_FILE_NAME, GateConfig, gate_config_from_toml
from cta.core.writer_graph import ASK_EVERY_ATTEMPTS, MAX_TOTAL_ATTEMPTS


@dataclass(frozen=True)
class RetryConfig:
    """작성 루프 반복 상한 — 기본값은 writer_graph의 v4 값(4회마다 묻기, 최대 8회)."""

    ask_every: int = ASK_EVERY_ATTEMPTS
    max_total: int = MAX_TOTAL_ATTEMPTS


@dataclass(frozen=True)
class CtaConfig:
    """cta.toml 전체. None은 "설정 안 함"이라 환경변수·코드 기본값이 쓰인다."""

    gates: GateConfig = field(default_factory=GateConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    gateway_timeout_sec: int | None = None  # None → CTA_GATEWAY_TIMEOUT 또는 llm/gateway.py 기본값
    model: str | None = None  # None → CTA_LLM_MODEL 또는 llm/config.py 기본값
    max_tokens_per_run: int | None = None  # None → 무제한. 넘으면 MeteredClient가 실행을 멈춘다


def load_config(project_root: str | Path) -> CtaConfig:
    """프로젝트 루트의 cta.toml을 읽는다. 없으면 전부 기본값.

    실패 시 동작: 반복 상한이 1 미만이거나 정수가 아니면 ValueError — 잘못된 설정으로
    조용히 돌지 않고 시작 시점에 멈춘다.
    """
    path = Path(project_root) / CONFIG_FILE_NAME
    if not path.is_file():
        return CtaConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    retry_data = data.get("retry", {})
    retry = RetryConfig(
        ask_every=int(retry_data.get("ask_every", ASK_EVERY_ATTEMPTS)),
        max_total=int(retry_data.get("max_total", MAX_TOTAL_ATTEMPTS)),
    )
    if retry.ask_every < 1 or retry.max_total < 1:
        raise ValueError(
            f"{CONFIG_FILE_NAME} [retry]: ask_every·max_total은 1 이상이어야 한다 "
            f"(ask_every={retry.ask_every}, max_total={retry.max_total})"
        )
    timeout = data.get("gateway", {}).get("timeout_sec")
    model = data.get("llm", {}).get("model")
    budget = data.get("budget", {}).get("max_tokens_per_run")
    return CtaConfig(
        gates=gate_config_from_toml(data.get("gates", {})),
        retry=retry,
        gateway_timeout_sec=int(timeout) if timeout is not None else None,
        model=str(model).strip() or None if model is not None else None,
        max_tokens_per_run=int(budget) if budget is not None else None,
    )
