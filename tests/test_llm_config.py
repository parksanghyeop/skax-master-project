"""llm/config·anthropic_client의 단위 테스트 — 네트워크·실제 키 없이 돈다.

검증: .env 파싱, 환경변수 우선순위, provider 선택, Claude 메시지 형식 변환.
"""

import pytest

from llm.anthropic_client import split_messages
from llm.client import ChatMessage
from llm.config import (
    ENV_PROVIDER,
    LlmConfigError,
    load_dotenv_into_env,
    make_llm_client,
    read_dotenv,
)


class TestDotenv:
    def test_주석과_빈_줄은_무시한다(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# 주석\n\nA=1\nB = x=y \n형식아님\n", encoding="utf-8")
        assert read_dotenv(env) == {"A": "1", "B": "x=y"}

    def test_파일이_없으면_빈_설정이다(self, tmp_path):
        assert read_dotenv(tmp_path / "없음.env") == {}

    def test_이미_있는_환경변수가_env_파일을_이긴다(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("CTA_TEST_KEY=파일값", encoding="utf-8")
        monkeypatch.setenv("CTA_TEST_KEY", "환경값")
        load_dotenv_into_env(env)
        import os

        assert os.environ["CTA_TEST_KEY"] == "환경값"


class TestMakeLlmClient:
    def test_기본은_claude_provider다(self, monkeypatch):
        monkeypatch.delenv(ENV_PROVIDER, raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        client, model = make_llm_client()
        assert type(client).__name__ == "ClaudeClient"
        assert model == "claude-opus-5"

    def test_gateway_provider를_고를_수_있다(self, monkeypatch):
        monkeypatch.setenv(ENV_PROVIDER, "gateway")
        monkeypatch.setenv("CTA_GATEWAY_URL", "http://gw.test")
        monkeypatch.setenv("CTA_GATEWAY_TOKEN", "t")
        client, model = make_llm_client()
        assert type(client).__name__ == "GatewayClient"
        assert model == "qwen"

    def test_모델은_설정으로_바꿀_수_있다(self, monkeypatch):
        monkeypatch.setenv(ENV_PROVIDER, "claude")
        monkeypatch.setenv("CTA_LLM_MODEL", "claude-haiku-4-5")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        _, model = make_llm_client()
        assert model == "claude-haiku-4-5"

    def test_모르는_provider는_안내와_함께_거부한다(self, monkeypatch):
        monkeypatch.setenv(ENV_PROVIDER, "gpt")
        with pytest.raises(LlmConfigError, match="claude"):
            make_llm_client()


class TestSplitMessages:
    def test_system은_파라미터로_나머지는_messages로_간다(self):
        system_text, api_messages = split_messages(
            [
                ChatMessage(role="system", content="역할 지시"),
                ChatMessage(role="user", content="질문"),
                ChatMessage(role="assistant", content="답"),
            ]
        )
        assert system_text == "역할 지시"
        assert api_messages == [
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "답"},
        ]

    def test_system이_없으면_빈_문자열이다(self):
        system_text, api_messages = split_messages([ChatMessage(role="user", content="q")])
        assert system_text == ""
        assert len(api_messages) == 1
