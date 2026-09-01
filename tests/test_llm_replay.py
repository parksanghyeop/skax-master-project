"""llm/ 계층의 record & replay 테스트 — M2 관문 "카세트 재생으로 결정적 테스트".

실제 게이트웨이 없이 Fake 클라이언트로 녹음하고, 재생이 같은 답을 돌려주는지,
그리고 어긋난 상황(카세트 없음·소진·요청 불일치)에서 실호출 폴백 없이
실패하는지(R7)를 검증한다.
"""

import pytest

from llm.client import ChatMessage, ChatResponse
from llm.gateway import GatewayClient, GatewayConfigError, build_payload, build_url
from llm.replay import CassetteError, RecordingClient, ReplayClient


class FakeLlm:
    """정해진 답을 돌려주는 클라이언트 대역 — 녹음 테스트의 '실호출' 역할."""

    def __init__(self, answers: list[str]):
        self._answers = list(answers)

    def chat(self, messages, model):
        return ChatResponse(content=self._answers.pop(0))


ASK = [ChatMessage(role="user", content="3+4는?")]


class TestRecordAndReplay:
    def test_녹음한_것을_재생하면_같은_답이_나온다(self, tmp_path):
        cassette = tmp_path / "cassette.json"
        recorder = RecordingClient(FakeLlm(["7"]), cassette)
        recorded = recorder.chat(ASK, model="qwen")

        replayer = ReplayClient(cassette)
        replayed = replayer.chat(ASK, model="qwen")
        assert replayed == recorded == ChatResponse(content="7")

    def test_여러_호출은_순서대로_재생된다(self, tmp_path):
        cassette = tmp_path / "cassette.json"
        recorder = RecordingClient(FakeLlm(["첫째", "둘째"]), cassette)
        recorder.chat(ASK, model="qwen")
        recorder.chat([ChatMessage(role="user", content="다음은?")], model="qwen")

        replayer = ReplayClient(cassette)
        assert replayer.chat(ASK, model="qwen").content == "첫째"
        assert (
            replayer.chat([ChatMessage(role="user", content="다음은?")], model="qwen").content
            == "둘째"
        )


class TestReplayFailsClosed:
    def test_카세트가_없으면_실패한다_실호출_폴백_금지(self, tmp_path):
        with pytest.raises(CassetteError, match="카세트 없음"):
            ReplayClient(tmp_path / "없는파일.json")

    def test_기록보다_많이_부르면_실패한다(self, tmp_path):
        cassette = tmp_path / "cassette.json"
        RecordingClient(FakeLlm(["7"]), cassette).chat(ASK, model="qwen")
        replayer = ReplayClient(cassette)
        replayer.chat(ASK, model="qwen")
        with pytest.raises(CassetteError, match="소진"):
            replayer.chat(ASK, model="qwen")

    def test_요청이_기록과_다르면_실패한다(self, tmp_path):
        cassette = tmp_path / "cassette.json"
        RecordingClient(FakeLlm(["7"]), cassette).chat(ASK, model="qwen")
        replayer = ReplayClient(cassette)
        with pytest.raises(CassetteError, match="불일치"):
            replayer.chat([ChatMessage(role="user", content="5+5는?")], model="qwen")


class TestGateway:
    def test_요청_본문에는_메시지만_들어간다(self):
        # 모델 선택은 본문이 아니라 URL(deployment)이 담당한다 (ADR-0011)
        assert build_payload(ASK) == {"messages": [{"role": "user", "content": "3+4는?"}]}

    def test_요청_경로는_azure_openai_호환이다(self):
        url = build_url("http://gw.test/", "gpt-4.1", "2024-12-01-preview")
        assert url == (
            "http://gw.test/openai/deployments/gpt-4.1/chat/completions"
            "?api-version=2024-12-01-preview"
        )

    def test_환경변수_없이_생성하면_거부한다(self, monkeypatch):
        monkeypatch.delenv("CTA_GATEWAY_URL", raising=False)
        monkeypatch.delenv("CTA_GATEWAY_API_KEY", raising=False)
        with pytest.raises(GatewayConfigError):
            GatewayClient()

    def test_카세트에_토큰이_남지_않는다(self, tmp_path, monkeypatch):
        cassette = tmp_path / "cassette.json"
        RecordingClient(FakeLlm(["7"]), cassette).chat(ASK, model="qwen")
        saved = cassette.read_text(encoding="utf-8")
        assert "TOKEN" not in saved and "Bearer" not in saved
