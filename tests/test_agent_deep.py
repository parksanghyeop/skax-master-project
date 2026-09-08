"""Deep Agent(메인 + 서브 3) — 대본 모델과 Fake 포트로 LLM·게이트웨이 없이 검증 (ADR-0024·0025).

대본 모델은 입력을 보지 않고 준비된 응답을 순서대로 낸다. 그래서 대본 순서가 곧 시나리오다:
메인 → task(explorer) → explorer 도구·보고 → task(writer) → writer 도구·보고 → 메인 마무리.
안전장치(원장)는 도구 호출 요청을 직접 만들어 단위로도 확인한다.
"""

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from scripted_model import ScriptedChatModel, ai

from cta.adapters.fake import (
    FakeCodeGraph,
    FakeQualityChecker,
    FakeSourceInspector,
    FakeTestWriter,
    ScriptedTestRunner,
    ScriptedUserGate,
)
from cta.core.agent.build import MAIN_TOOLS, build_agent, run_agent
from cta.core.agent.limits import HIDDEN_TOOLS, HideWriteTools, RunLedger
from cta.core.agent.ports import AgentPorts
from cta.core.agent.subagents import SUBAGENT_TOOLS, build_subagents
from cta.core.agent.tools import ASK_USER_TOOL, NATIVE_TOOL_NAMES, make_tools
from cta.core.ports import RunResult, UserReply
from cta.core.user_gate import InterruptUserGate

PASS = RunResult(passed=True, summary="Tests run: 2, Failures: 0")
FAIL_A = RunResult(passed=False, summary="[ERROR] expected 3 but was 4")
FAIL_B = RunResult(passed=False, summary="[ERROR] NullPointerException")
TEST_PATH = "src/test/DivideTest"


def call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id}


def task(subagent: str, description: str, call_id: str) -> dict:
    return call("task", {"description": description, "subagent_type": subagent}, call_id)


def make_ports(tmp_path, model, runs: list[RunResult], gate=None) -> AgentPorts:
    return AgentPorts(
        inspector=FakeSourceInspector({"Calc#divide": "int divide(int a, int b)"}),
        graph=FakeCodeGraph({"similar_tests": "본보기: divide_byZero_throws"}),
        writer=FakeTestWriter(),
        runner=ScriptedTestRunner(runs),
        checker=FakeQualityChecker("통과: 새 테스트, assert 2개"),
        gate=gate or ScriptedUserGate(),
        model=model,
        project_root=tmp_path,
        language="어떤 언어",
        framework="어떤 프레임워크",
        style_notes="관례 한 줄",
    )


def run(ports: AgentPorts, ask_user=None, **limits) -> dict:
    app, ledger = build_agent(ports, checkpointer=MemorySaver(), **limits)
    return run_agent(
        app,
        ledger,
        ports,
        instruction="divide에 새 테스트",
        context="[재료] 확인 항목 2개",
        target="Calc#divide",
        test_path=TEST_PATH,
        selector="DivideTest",
        thread_id="t1",
        ask_user=ask_user or (lambda q: UserReply(action="continue")),
    )


class TestHappyPath:
    def test_탐색_작성_실행_품질확인이_서브를_거쳐_끝난다(self, tmp_path):
        model = ScriptedChatModel(
            script=[
                ai(tool_calls=[task("explorer", "Calc#divide 조사", "m1")]),
                ai(tool_calls=[call("inspect_target", {"target": "Calc#divide"}, "e1")]),
                ai("[대상 형태] int divide(int a, int b)"),
                ai(
                    tool_calls=[
                        task(
                            "writer",
                            "테스트 작성 — 경로 src/test/DivideTest, selector DivideTest",
                            "m2",
                        )
                    ]
                ),
                ai(
                    tool_calls=[
                        call("write_test", {"path": TEST_PATH, "code": "// 시도 1\n"}, "w1")
                    ]
                ),
                ai(tool_calls=[call("run_tests", {"selector": "DivideTest"}, "w2")]),
                ai("결과: 통과\n파일: src/test/DivideTest\n시도: 1회"),
                ai(tool_calls=[call("check_quality", {"path": TEST_PATH}, "m3")]),
                ai("통과 — 품질 확인 완료"),
            ]
        )
        ports = make_ports(tmp_path, model, [PASS])
        state = run(ports)
        assert state["status"] == "passed"
        assert state["attempts"] == 1 and len(state["history"]) == 1
        assert state["history"][0]["run_result"].startswith("통과")
        assert state["test_code"] == "// 시도 1\n"
        assert ports.writer.writes == [(TEST_PATH, "// 시도 1\n")]
        assert state["quality"].startswith("통과")
        assert state["report"] == ""
        # 서브에이전트는 새 컨텍스트다 — explorer의 첫 호출은 메인 대화가 아니라 task 설명만 받는다
        explorer_first_call = model.calls[1]
        assert any("Calc#divide 조사" in str(m.content) for m in explorer_first_call)

    def test_통과했는데_메인이_품질확인을_빠뜨리면_하네스가_대신_부른다(self, tmp_path):
        model = ScriptedChatModel(
            script=[
                ai(tool_calls=[task("writer", "작성", "m1")]),
                ai(tool_calls=[call("write_test", {"path": TEST_PATH, "code": "// c\n"}, "w1")]),
                ai(tool_calls=[call("run_tests", {"selector": "DivideTest"}, "w2")]),
                ai("결과: 통과"),
                ai("끝"),  # check_quality 없이 종료
            ]
        )
        state = run(make_ports(tmp_path, model, [PASS]))
        assert state["status"] == "passed" and state["quality"].startswith("통과")


class TestLimitsThroughAgent:
    def test_소프트_한도에서_실행이_거부되고_메인이_묻고_중지하면_한계_보고다(self, tmp_path):
        gate = ScriptedUserGate([UserReply(action="stop")])
        model = ScriptedChatModel(
            script=[
                ai(tool_calls=[task("writer", "작성", "m1")]),
                ai(tool_calls=[call("write_test", {"path": TEST_PATH, "code": "// 1\n"}, "w1")]),
                ai(tool_calls=[call("run_tests", {"selector": "DivideTest"}, "w2")]),  # 실패 A
                ai(tool_calls=[call("write_test", {"path": TEST_PATH, "code": "// 2\n"}, "w3")]),
                ai(
                    tool_calls=[call("run_tests", {"selector": "DivideTest"}, "w4")]
                ),  # 실패 B → 소프트 한도(2회)
                ai(
                    tool_calls=[call("run_tests", {"selector": "DivideTest"}, "w5")]
                ),  # 거부돼야 한다
                ai("결과: 실패\n[안내]: 사용자 확인이 필요하다"),
                ai(tool_calls=[call("ask_user", {"question": "2회 실패했다. 계속?"}, "m2")]),
                ai(tool_calls=[call("report_finding", {"finding": "사용자 중지"}, "m3")]),
                ai("한계 보고로 끝"),
            ]
        )
        ports = make_ports(tmp_path, model, [FAIL_A, FAIL_B, PASS], gate=gate)
        state = run(ports, ask_every=2, max_total=8)
        assert state["status"] == "reported"
        assert state["attempts"] == 2  # 세 번째 run_tests는 실행되지 않았다
        assert ports.runner.calls == ["DivideTest", "DivideTest"]
        assert gate.questions == ["2회 실패했다. 계속?"]
        assert "사용자 중지" in state["report"]

    def test_interrupt_게이트로_실제_멈춤과_재개가_된다(self, tmp_path):
        model = ScriptedChatModel(
            script=[
                ai(tool_calls=[call("ask_user", {"question": "계속할까?"}, "m1")]),
                ai("끝"),
            ]
        )
        ports = make_ports(tmp_path, model, [], gate=InterruptUserGate())
        answers: list[str] = []

        def ask(question: str) -> UserReply:
            answers.append(question)
            return UserReply(action="continue", hint="mock을 써라")

        run(ports, ask_user=ask)
        assert answers == ["계속할까?"]
        # 재개 뒤 도구 결과(힌트)가 메인의 다음 호출에 들어갔다
        assert any("mock을 써라" in str(m.content) for m in model.calls[-1])


class TestWriteToolsAreDenied:
    def test_내장_쓰기_도구는_거부되고_파일이_생기지_않는다(self, tmp_path):
        model = ScriptedChatModel(
            script=[
                ai(
                    tool_calls=[
                        call("write_file", {"file_path": "/Hack.txt", "content": "x"}, "m1")
                    ]
                ),
                ai("끝"),
            ]
        )
        run(make_ports(tmp_path, model, []))
        denied = [m for m in model.calls[-1] if isinstance(m, ToolMessage)]
        assert denied and "permission denied" in str(denied[-1].content)
        assert not (tmp_path / "Hack.txt").exists()

    def test_모델에게_보이는_도구_목록에서_쓰기_도구가_빠진다(self):
        class Req:
            tools = [
                {"name": n} for n in ("read_file", "write_file", "edit_file", "delete", "run_tests")
            ]

            def override(self, **kw):
                return kw["tools"]

        seen = HideWriteTools().wrap_model_call(Req(), lambda kept: kept)
        assert [t["name"] for t in seen] == ["read_file", "run_tests"]


class TestToolInventory:
    """ADR-0025의 불변식 — 고유 도구 6개, ask_user는 메인만, 쓰기는 writer만."""

    def test_고유_도구_6개와_ask_user(self, tmp_path):
        tools = make_tools(make_ports(tmp_path, ScriptedChatModel(), []))
        assert set(tools) == NATIVE_TOOL_NAMES | {ASK_USER_TOOL}
        assert len(NATIVE_TOOL_NAMES) == 6

    def test_서브_배치_쓰기는_writer만_ask_user는_없음(self, tmp_path):
        ports = make_ports(tmp_path, ScriptedChatModel(), [])
        specs = build_subagents(make_tools(ports), RunLedger(), ports)
        by_name = {s["name"]: {t.name for t in s["tools"]} for s in specs}
        assert by_name["writer"] == {"write_test", "run_tests"}
        assert by_name["explorer"] == by_name["diagnoser"] == {"inspect_target", "query_code_graph"}
        assert by_name["general-purpose"] == set()
        assert all(ASK_USER_TOOL not in names for names in by_name.values())
        assert ASK_USER_TOOL in MAIN_TOOLS and "write_test" not in MAIN_TOOLS
        assert set(SUBAGENT_TOOLS) == set(by_name)
        assert set(HIDDEN_TOOLS) == {"write_file", "edit_file", "delete"}


def _request(name: str, args: dict) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "c"}, tool=None, state={}, runtime=None
    )


def _handler(outcome: str):
    return lambda req: ToolMessage(content=outcome, tool_call_id="c", name=req.tool_call["name"])


class TestRunLedgerUnit:
    def test_하드_캡에_닿으면_실행하지_않고_거부한다(self):
        ledger = RunLedger(ask_every=10, max_total=2)
        first = ledger.wrap_tool_call(_request("run_tests", {"selector": "T"}), _handler("실패: 1"))
        second = ledger.wrap_tool_call(
            _request("run_tests", {"selector": "T"}), _handler("실패: 2")
        )
        assert "실행 상한" in second.content and ledger.blocked == "hard"
        calls = []
        third = ledger.wrap_tool_call(
            _request("run_tests", {"selector": "T"}), lambda r: calls.append(r)
        )
        assert calls == [] and "실행 거부" in third.content and ledger.attempts == 2
        assert "[안내]" not in first.content

    def test_같은_실패가_반복되면_질문이_필요해진다(self):
        ledger = RunLedger(ask_every=10, max_total=8)
        ledger.wrap_tool_call(_request("run_tests", {"selector": "T"}), _handler("실패: 같음"))
        again = ledger.wrap_tool_call(
            _request("run_tests", {"selector": "T"}), _handler("실패: 같음")
        )
        assert ledger.needs_ask and "같은 실패" in again.content
        # ask_user가 "계속"이면 풀린다
        ledger.wrap_tool_call(
            _request("ask_user", {"question": "?"}), _handler("사용자 답: 계속. 힌트: (없음)")
        )
        assert not ledger.needs_ask

    def test_환경_문제는_묻지_않고_막는다(self):
        ledger = RunLedger()
        result = ledger.wrap_tool_call(
            _request("run_tests", {"selector": "T"}), _handler("실패: 시간 초과")
        )
        assert ledger.blocked == "impossible" and "통과 불가능" in result.content

    def test_사용자_중지_뒤에는_실행이_거부된다(self):
        ledger = RunLedger()
        ledger.wrap_tool_call(
            _request("ask_user", {"question": "?"}), _handler("사용자 답: 중지 — 끝내라")
        )
        refused = ledger.wrap_tool_call(_request("run_tests", {"selector": "T"}), _handler("통과"))
        assert ledger.blocked == "stopped" and "중지" in refused.content and ledger.attempts == 0

    def test_상한이_1_미만이면_조립_시점에_거부한다(self):
        with pytest.raises(ValueError):
            RunLedger(ask_every=0)
