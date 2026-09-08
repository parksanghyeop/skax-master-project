"""LangChain 모델 생성(make_chat_model) — 환경변수 규칙과 시크릿 비노출 (ADR-0024 결정 5)."""

import pytest

from cta.llm.chat_model import make_chat_model
from cta.llm.gateway import GatewayConfigError


def test_주소_키가_없으면_실패하고_메시지에_값이_없다(monkeypatch, tmp_path):
    monkeypatch.delenv("CTA_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CTA_GATEWAY_API_KEY", raising=False)
    with pytest.raises(GatewayConfigError, match="CTA_GATEWAY_URL"):
        make_chat_model(dotenv_path=tmp_path / "none.env")


def test_환경변수로_모델이_만들어지고_deployment가_URL에_들어간다(monkeypatch, tmp_path):
    monkeypatch.setenv("CTA_GATEWAY_URL", "https://gw.example")
    monkeypatch.setenv("CTA_GATEWAY_API_KEY", "fake-key-value")
    monkeypatch.delenv("CTA_LLM_MODEL", raising=False)
    monkeypatch.delenv("CTA_GATEWAY_TIMEOUT", raising=False)
    model, deployment = make_chat_model(
        dotenv_path=tmp_path / "none.env", model_default="gpt-5", timeout_default=42
    )
    assert deployment == "gpt-5"
    assert model.deployment_name == "gpt-5"
    assert model.request_timeout == 42
    assert model.reasoning_effort == "low"  # 추론 모델 → 기본 low(ADR-0023)
    assert "fake-key-value" not in repr(model)


def test_비추론_모델에는_추론_강도를_보내지_않는다(monkeypatch, tmp_path):
    monkeypatch.setenv("CTA_GATEWAY_URL", "https://gw.example")
    monkeypatch.setenv("CTA_GATEWAY_API_KEY", "k")
    monkeypatch.delenv("CTA_LLM_MODEL", raising=False)
    model, _ = make_chat_model(dotenv_path=tmp_path / "none.env", model_default="gpt-4.1")
    assert model.reasoning_effort is None
