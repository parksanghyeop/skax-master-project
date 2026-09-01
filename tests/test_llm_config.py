"""llm/config의 단위 테스트 — 네트워크·실제 키 없이 돈다.

검증: .env 파싱, 환경변수 우선순위, 게이트웨이 클라이언트·deployment 선택.
"""

import os

from cta.llm.config import (
    DEFAULT_MODEL,
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
        assert os.environ["CTA_TEST_KEY"] == "환경값"

    def test_경로_생략_시_현재_폴더의_env를_읽는다(self, tmp_path, monkeypatch):
        # 설치형 CLI 계약: 자바 프로젝트 폴더에서 실행하면 그 폴더의 .env가 잡힌다
        (tmp_path / ".env").write_text("CTA_CWD_KEY=현재폴더값", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CTA_CWD_KEY", raising=False)
        load_dotenv_into_env()
        assert os.environ.pop("CTA_CWD_KEY") == "현재폴더값"


class TestMakeLlmClient:
    def test_게이트웨이_클라이언트와_기본_deployment를_만든다(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CTA_GATEWAY_URL", "http://gw.test")
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", "atl-test-not-real")
        monkeypatch.delenv("CTA_LLM_MODEL", raising=False)
        # 임시 경로: 개발자의 실제 .env가 테스트 결과를 바꾸지 않게 격리한다
        client, model = make_llm_client(dotenv_path=tmp_path / "없음.env")
        assert type(client).__name__ == "GatewayClient"
        assert model == DEFAULT_MODEL

    def test_deployment는_설정으로_바꿀_수_있다(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CTA_GATEWAY_URL", "http://gw.test")
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", "atl-test-not-real")
        monkeypatch.setenv("CTA_LLM_MODEL", "gpt-5-mini")
        _, model = make_llm_client(dotenv_path=tmp_path / "없음.env")
        assert model == "gpt-5-mini"
