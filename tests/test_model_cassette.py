"""카세트 v2(모델 호출 미들웨어) — 녹음→재생 왕복, 폴백 없음, 토큰 합산·예산 (ADR-0024 결정 5).

LangChain `create_agent` + 대본 모델 + 도구 1개로 도구 호출형 멀티턴을 만들고, 같은 입력을
재생 모드(NoCallChatModel)로 다시 돌려 결과가 같은지 본다. 게이트웨이 없이 돈다.
"""

import json

import pytest
from langchain.agents import create_agent
from langchain_core.tools import tool
from scripted_model import ScriptedChatModel, ai

from cta.llm.chat_model import NoCallChatModel
from cta.llm.metering import BudgetExceededError, MeteringModelMiddleware
from cta.llm.model_cassette import (
    CASSETTE_VERSION,
    RecordingModelMiddleware,
    ReplayModelMiddleware,
    request_key,
)
from cta.llm.replay import CassetteError


@tool
def run_tests(selector: str) -> str:
    """지정한 테스트만 실행한다."""
    return f"통과: {selector}"


def _script() -> list:
    return [
        ai(
            tool_calls=[{"name": "run_tests", "args": {"selector": "CalcTest"}, "id": "call_1"}],
            tokens=10,
        ),
        ai("끝: CalcTest 통과", tokens=7),
    ]


def _run(model, middleware, prompt="CalcTest를 실행하라") -> str:
    agent = create_agent(
        model, tools=[run_tests], system_prompt="너는 테스트 실행기다", middleware=middleware
    )
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


class TestRecordThenReplay:
    def test_녹음한_카세트로_재생하면_같은_결과가_나온다(self, tmp_path):
        cassette = tmp_path / "run.json"
        recorded = _run(ScriptedChatModel(script=_script()), [RecordingModelMiddleware(cassette)])
        assert recorded == "끝: CalcTest 통과"
        data = json.loads(cassette.read_text(encoding="utf-8"))
        assert data["version"] == CASSETTE_VERSION and len(data["entries"]) == 2
        # 첫 호출 기록에 도구 호출이, 요청 키에 도구 이름이 들어 있다
        assert data["entries"][0]["response"][0]["data"]["tool_calls"][0]["name"] == "run_tests"
        assert data["entries"][0]["request"]["tools"] == ["run_tests"]

        replay = ReplayModelMiddleware(cassette)
        replayed = _run(NoCallChatModel(deployment_name=replay.deployment), [replay])
        assert replayed == recorded

    def test_요청이_다르면_재생이_거부된다(self, tmp_path):
        cassette = tmp_path / "run.json"
        _run(ScriptedChatModel(script=_script()), [RecordingModelMiddleware(cassette)])
        replay = ReplayModelMiddleware(cassette)
        with pytest.raises(CassetteError, match="불일치"):
            _run(NoCallChatModel(deployment_name=replay.deployment), [replay], prompt="다른 질문")

    def test_기록이_소진되면_재생이_거부된다(self, tmp_path):
        cassette = tmp_path / "run.json"
        _run(ScriptedChatModel(script=_script()), [RecordingModelMiddleware(cassette)])
        data = json.loads(cassette.read_text(encoding="utf-8"))
        data["entries"] = data["entries"][:1]  # 두 번째 호출 기록을 지운다
        cassette.write_text(json.dumps(data), encoding="utf-8")
        replay = ReplayModelMiddleware(cassette)
        with pytest.raises(CassetteError, match="소진"):
            _run(NoCallChatModel(deployment_name=replay.deployment), [replay])

    def test_카세트가_없으면_실호출로_폴백하지_않고_실패한다(self, tmp_path):
        with pytest.raises(CassetteError, match="없음"):
            ReplayModelMiddleware(tmp_path / "missing.json")

    def test_v1_형식은_읽지_않는다(self, tmp_path):
        cassette = tmp_path / "old.json"
        cassette.write_text("[]", encoding="utf-8")  # v1은 배열이다
        with pytest.raises(CassetteError, match="형식"):
            ReplayModelMiddleware(cassette)

    def test_미들웨어를_비켜_간_실호출은_예외다(self):
        with pytest.raises(RuntimeError, match="실호출"):
            NoCallChatModel().invoke("hi")


class TestRequestKey:
    def test_메시지_id는_키에_들어가지_않는다(self):
        from langchain.agents.middleware import ModelRequest
        from langchain_core.messages import HumanMessage, SystemMessage

        def make(msg_id):
            return ModelRequest(
                model=NoCallChatModel(),
                messages=[HumanMessage(content="q", id=msg_id)],
                system_message=SystemMessage(content="s"),
                tool_choice=None,
                tools=[run_tests],
                response_format=None,
                state={},
                runtime=None,
                model_settings={},
            )

        assert request_key(make("a")) == request_key(make("b"))
        assert request_key(make("a"))["model"] == "replay"


class TestMetering:
    def test_실호출과_재생_모두에서_토큰을_합산한다(self, tmp_path):
        cassette = tmp_path / "run.json"
        meter = MeteringModelMiddleware()
        _run(ScriptedChatModel(script=_script()), [meter, RecordingModelMiddleware(cassette)])
        assert meter.calls == 2 and meter.total_tokens == 17
        assert meter.breakdown()["prompt"] == 15 and meter.breakdown()["completion"] == 2

        meter2 = MeteringModelMiddleware()
        replay = ReplayModelMiddleware(cassette)
        _run(NoCallChatModel(deployment_name=replay.deployment), [meter2, replay])
        assert meter2.calls == 2 and meter2.total_tokens == 17

    def test_예산에_닿으면_호출_전에_멈춘다(self):
        meter = MeteringModelMiddleware(max_tokens=10)
        model = ScriptedChatModel(script=_script())
        with pytest.raises(BudgetExceededError):
            _run(model, [meter])
        # 첫 호출(10토큰)은 됐고, 두 번째는 호출 전에 막혔다 — 대본은 하나만 소비
        assert meter.calls == 1 and model.cursor == 1
