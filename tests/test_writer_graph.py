"""테스트 작성 서브그래프(core/writer_graph)의 단위 테스트 — 전부 Fake로 돈다.

검증하는 흐름(v4 2.3): 첫 시도 통과 / 실패 후 재시도 끝 통과 / 소프트 한도에서
사용자에게 묻기(자동 계속 스텁) / 하드 한도에서 한계 보고 / 사용자 중지.
"""

from adapters.fake import (
    FakeCodeGraph,
    FakeQualityChecker,
    FakeSourceInspector,
    FakeTestWriter,
    ScriptedGenerator,
    ScriptedTestRunner,
    ScriptedUserGate,
)
from core.ports import RunResult, UserReply
from core.writer_graph import (
    ASK_EVERY_ATTEMPTS,
    MAX_TOTAL_ATTEMPTS,
    WriterPorts,
    build_writer_graph,
)

PASS = RunResult(passed=True, summary="Tests run: 2, Failures: 0")
FAIL = RunResult(passed=False, summary="[ERROR] expected 3 but was 4")


def make_ports(run_script: list[RunResult], gate: ScriptedUserGate | None = None) -> WriterPorts:
    return WriterPorts(
        inspector=FakeSourceInspector({"Calc#divide": "int divide(int a, int b)"}),
        graph=FakeCodeGraph({"similar_tests": "본보기: divide_byZero_throws"}),
        writer=FakeTestWriter(),
        runner=ScriptedTestRunner(run_script),
        checker=FakeQualityChecker("통과: 새 테스트, assert 2개"),
        gate=gate or ScriptedUserGate(),
        generator=ScriptedGenerator([f"// 시도 {i}\n" for i in range(1, 10)]),
    )


def initial_state() -> dict:
    return {
        "instruction": "divide에 새 테스트",
        "target": "Calc#divide",
        "test_path": "src/test/DivideTest",
        "selector": "DivideTest",
        "context": "",
        "test_code": "",
        "write_result": "",
        "last_run": "",
        "attempts": 0,
        "quality": "",
        "report": "",
        "status": "working",
    }


class TestHappyPath:
    def test_첫_시도_통과면_품질_확인까지_간다(self):
        ports = make_ports([PASS])
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "passed"
        assert final["attempts"] == 1
        assert final["quality"].startswith("통과")
        assert "[대상 조사]" in final["context"]  # 정보 수집이 프롬프트 재료를 만들었다

    def test_실패하면_실패_내용을_들고_재시도한다(self):
        ports = make_ports([FAIL, PASS])
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "passed"
        assert final["attempts"] == 2
        # 재시도 프롬프트에 직전 실패가 들어갔는지 — 자기 수정의 근거
        assert "expected 3 but was 4" in ports.generator.calls[1]["last_failure"]


class TestLimitsAndGate:
    def test_소프트_한도마다_사용자에게_묻는다(self):
        gate = ScriptedUserGate()  # 항상 "계속"
        ports = make_ports([FAIL] * MAX_TOTAL_ATTEMPTS, gate)
        final = build_writer_graph(ports).invoke(initial_state())
        # 3회째 실패에서 한 번 물었고(자동 계속), 6회째는 묻지 않고 하드 캡으로 끝났다
        assert len(gate.questions) == 1
        assert final["status"] == "reported"
        assert final["attempts"] == MAX_TOTAL_ATTEMPTS
        assert final["report"].startswith("한계 보고")

    def test_사용자가_중지하면_한계_보고로_정상_종료한다(self):
        gate = ScriptedUserGate([UserReply(action="stop")])
        ports = make_ports([FAIL] * 10, gate)
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "reported"
        assert final["attempts"] == ASK_EVERY_ATTEMPTS  # 첫 질문 시점에 멈췄다

    def test_사용자_힌트는_다음_시도의_재료에_들어간다(self):
        gate = ScriptedUserGate([UserReply(action="continue", hint="0 나누기를 먼저 시험하라")])
        ports = make_ports([FAIL] * ASK_EVERY_ATTEMPTS + [PASS], gate)
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "passed"
        assert "0 나누기를 먼저 시험하라" in final["context"]
