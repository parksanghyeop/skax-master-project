"""cta.toml 설정(core/config.py)과 우선순위(환경변수 > .env > cta.toml > 기본값) 테스트."""

import os

import pytest

from cta.core.config import CtaConfig, load_config
from cta.core.writer_graph import ASK_EVERY_ATTEMPTS, MAX_TOTAL_ATTEMPTS
from cta.llm.config import make_llm_client

FULL_TOML = """
[gates]
line_min = 0.9
[retry]
ask_every = 2
max_total = 5
[gateway]
timeout_sec = 600
[llm]
model = "gpt-5"
[budget]
max_tokens_per_run = 50000
"""


class TestLoadConfig:
    def test_파일이_없으면_전부_기본값이다(self, tmp_path):
        config = load_config(tmp_path)
        assert config == CtaConfig()
        assert (config.retry.ask_every, config.retry.max_total) == (
            ASK_EVERY_ATTEMPTS,
            MAX_TOTAL_ATTEMPTS,
        )
        assert config.gateway_timeout_sec is None and config.model is None
        assert config.max_tokens_per_run is None  # 무제한

    def test_절마다_값을_읽고_안_적은_값은_기본값이다(self, tmp_path):
        (tmp_path / "cta.toml").write_text(FULL_TOML, encoding="utf-8")
        config = load_config(tmp_path)
        assert config.gates.line_min == 0.9
        assert config.gates.branch_min == 0.70  # 안 적음 → 기본값
        assert (config.retry.ask_every, config.retry.max_total) == (2, 5)
        assert config.gateway_timeout_sec == 600
        assert config.model == "gpt-5"
        assert config.max_tokens_per_run == 50000

    def test_반복_상한이_1_미만이면_시작_시점에_멈춘다(self, tmp_path):
        (tmp_path / "cta.toml").write_text("[retry]\nmax_total = 0\n", encoding="utf-8")
        with pytest.raises(ValueError, match="cta.toml"):
            load_config(tmp_path)


class TestPrecedence:
    """cta.toml 값은 환경변수의 기본값 자리에만 놓인다 — 환경변수·.env가 있으면 그쪽이 이긴다."""

    @pytest.fixture(autouse=True)
    def gateway_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CTA_GATEWAY_URL", "https://gateway.example")
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", "atl-test-key-000000")
        monkeypatch.delenv("CTA_LLM_MODEL", raising=False)
        monkeypatch.delenv("CTA_GATEWAY_TIMEOUT", raising=False)
        self.no_dotenv = tmp_path / "없는.env"

    def test_환경변수가_없으면_cta_toml_값이_쓰인다(self):
        client, model = make_llm_client(self.no_dotenv, model_default="gpt-5", timeout_default=600)
        assert model == "gpt-5"
        assert client.timeout == 600

    def test_환경변수가_있으면_cta_toml_값을_덮지_않는다(self, monkeypatch):
        monkeypatch.setenv("CTA_LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("CTA_GATEWAY_TIMEOUT", "120")
        client, model = make_llm_client(self.no_dotenv, model_default="gpt-5", timeout_default=600)
        assert model == "gpt-4.1-mini"
        assert client.timeout == 120

    def test_cta_toml_값은_환경변수에_남지_않는다(self):
        # 오래 사는 프로세스(MCP 서버)가 다음 프로젝트를 다룰 때 이전 프로젝트 설정이 이기면 안 된다
        make_llm_client(self.no_dotenv, model_default="gpt-5", timeout_default=600)
        assert "CTA_LLM_MODEL" not in os.environ
        assert "CTA_GATEWAY_TIMEOUT" not in os.environ
        client, model = make_llm_client(self.no_dotenv, model_default="gpt-4.1", timeout_default=90)
        assert (model, client.timeout) == ("gpt-4.1", 90)

    def test_dotenv가_있으면_cta_toml보다_이긴다(self, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text("CTA_LLM_MODEL=gpt-4.1\n", encoding="utf-8")
        _, model = make_llm_client(dotenv, model_default="gpt-5")
        assert model == "gpt-4.1"
