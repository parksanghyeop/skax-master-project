"""시크릿 3 테스트 (v4 6.6) — ① 키는 환경변수·.env만 ② 샌드박스 미전달 ③ 출력·기록에서 가림.

①은 tests/test_llm_config.py(.env 로딩·환경변수 우선)와 GatewayConfigError로 이미 고정돼 있다.
여기서는 ②·③과 토큰 예산을 고정한다.
"""

import json

import pytest

from cta.llm.client import ChatMessage, ChatResponse
from cta.llm.gateway import GatewayClient, GatewayConfigError
from cta.llm.masking import MASK, mask_secrets
from cta.llm.metering import BudgetExceededError, MeteredClient
from cta.llm.replay import RecordingClient
from cta.sandbox.docker_sandbox import Mount, build_run_args

SECRET = "atl-supersecret-1234567890"


class _EchoClient:
    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        return ChatResponse(content="// ok", usage_tokens=100)


class TestSandboxDoesNotReceiveSecrets:
    """② 호스트 환경변수(게이트웨이 키)가 컨테이너로 들어가는 경로를 두지 않는다."""

    def test_docker_run_인자에_환경변수_전달_옵션이_없다(self, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", SECRET)
        args = build_run_args(
            "maven:3-eclipse-temurin-21",
            ["mvn", "-o", "test"],
            [Mount("/host/proj", "/work"), Mount("/host/m2", "/root/.m2", read_only=True)],
            "/work",
        )
        assert "-e" not in args and "--env" not in args and "--env-file" not in args
        assert SECRET not in " ".join(args)
        assert args[:5] == ["docker", "run", "--rm", "--network", "none"]  # 기본 네트워크 차단
        assert "/host/m2:/root/.m2:ro" in args

    def test_네트워크는_명시적으로만_켠다(self):
        args = build_run_args("img", ["true"], [], "/work", network_enabled=True)
        assert "--network" not in args


class TestMasking:
    """③ 어떤 문자열에 키가 섞여도 화면에는 나오지 않는다."""

    def test_환경변수의_키_값을_가린다(self, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", SECRET)
        masked = mask_secrets(f"호출 실패: api-key={SECRET} 거부")
        assert masked == f"호출 실패: api-key={MASK} 거부"

    def test_환경변수에_없어도_키_모양이면_가린다(self, monkeypatch):
        monkeypatch.delenv("CTA_GATEWAY_API_KEY", raising=False)
        assert mask_secrets("헤더 atl-abcdef123456 포함") == f"헤더 atl-{MASK} 포함"

    def test_키가_없는_문장은_그대로다(self, monkeypatch):
        monkeypatch.delenv("CTA_GATEWAY_API_KEY", raising=False)
        assert mask_secrets("게이트웨이 호출 실패: timed out") == "게이트웨이 호출 실패: timed out"

    def test_저장된_호출_기록에_키가_들어가지_않는다(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", SECRET)
        cassette = tmp_path / "rec.json"
        client = RecordingClient(_EchoClient(), cassette)
        client.chat([ChatMessage("user", "테스트를 만들라")], "gpt-5")
        text = cassette.read_text(encoding="utf-8")
        assert SECRET not in text
        assert json.loads(text)[0]["request"]["model"] == "gpt-5"

    def test_키가_없으면_생성_시점에_실패한다(self, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_URL", "https://gateway.example")
        monkeypatch.delenv("CTA_GATEWAY_API_KEY", raising=False)
        with pytest.raises(GatewayConfigError):
            GatewayClient()


class TestTokenBudget:
    def test_예산에_닿으면_다음_호출을_하지_않는다(self):
        client = MeteredClient(_EchoClient(), max_tokens=150)
        client.chat([ChatMessage("user", "1")], "m")  # 누적 100 < 150 → 호출
        client.chat([ChatMessage("user", "2")], "m")  # 누적 100 → 호출 후 200
        with pytest.raises(BudgetExceededError, match="200"):
            client.chat([ChatMessage("user", "3")], "m")
        assert client.calls == 2

    def test_예산이_없으면_무제한이다(self):
        client = MeteredClient(_EchoClient())
        for _ in range(5):
            client.chat([ChatMessage("user", "x")], "m")
        assert client.total_tokens == 500


class TestDockerMissing:
    def test_docker_실행_파일이_없으면_메시지에_docker가_들어간다(self, monkeypatch):
        # Windows 원문 "[WinError 2] 지정된 파일을 찾을 수 없습니다"에는 docker가 없다 —
        # 그대로 올라오면 오류 안내(cli/hints)가 Docker 문제로 알아보지 못한다
        import cta.sandbox.docker_sandbox as sandbox_module
        from cta.sandbox.docker_sandbox import DockerSandbox

        def missing(*_args, **_kwargs):
            raise FileNotFoundError(2, "지정된 파일을 찾을 수 없습니다")

        monkeypatch.setattr(sandbox_module.subprocess, "run", missing)
        with pytest.raises(FileNotFoundError, match="docker"):
            DockerSandbox().run("img", ["true"], [], "/work")
