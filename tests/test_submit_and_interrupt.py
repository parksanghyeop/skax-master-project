"""M6 게이트 재시도 루프(core/submit)와 interrupt 실연결의 단위 테스트 — 전부 Fake."""

from langgraph.checkpoint.memory import MemorySaver

from cta.adapters.fake import (
    FakeCodeGraph,
    FakeQualityChecker,
    FakeSourceInspector,
    FakeTestWriter,
    ScriptedGenerator,
    ScriptedTestRunner,
)
from cta.core.gates import GateResult
from cta.core.ports import RunResult, UserReply
from cta.core.submit import generate_with_gates
from cta.core.writer_graph import (
    InterruptUserGate,
    WriterPorts,
    build_writer_graph,
    invoke_with_interrupts,
)

PASS = RunResult(passed=True, summary="Tests run: 1, Failures: 0")
FAIL_A = RunResult(passed=False, summary="[ERROR] 컴파일 오류")
FAIL_B = RunResult(passed=False, summary="[ERROR] 컴파일 오류")  # 같은 실패 반복용


def make_ports(run_script, gate):
    return WriterPorts(
        inspector=FakeSourceInspector({"Calc#divide": "int divide(int a, int b)"}),
        graph=FakeCodeGraph({"similar_tests": "본보기"}),
        writer=FakeTestWriter(),
        runner=ScriptedTestRunner(run_script),
        checker=FakeQualityChecker(),
        gate=gate,
        generator=ScriptedGenerator([f"// 시도 {i}\n" for i in range(1, 10)]),
    )


def initial_state(instruction="divide에 새 테스트"):
    return {
        "instruction": instruction,
        "target": "Calc#divide",
        "test_path": "src/test/DivideTest",
        "selector": "DivideTest",
        "context": "",
        "test_code": "",
        "write_result": "",
        "last_run": "",
        "prev_run": "",
        "attempts": 0,
        "quality": "",
        "report": "",
        "status": "working",
    }


class TestInterruptRoundtrip:
    """정지 → 사용자 답 → 같은 지점부터 재개 (M6 관문: escalate→resolve→재개의 그래프 절반)."""

    def test_같은_실패_반복에서_정지하고_힌트로_재개해_통과한다(self):
        ports = make_ports([FAIL_A, FAIL_B, PASS], InterruptUserGate())
        app = build_writer_graph(ports, checkpointer=MemorySaver())
        questions: list[str] = []

        def ask_user(question: str) -> UserReply:
            questions.append(question)
            return UserReply(action="continue", hint="경계값을 시험하라")

        final = invoke_with_interrupts(app, initial_state(), "t1", ask_user)
        assert len(questions) == 1
        assert "2회 실패" in questions[0]  # 질문에 맥락이 담긴다
        assert final["status"] == "passed"
        assert "경계값을 시험하라" in final["context"]  # 힌트가 재개 후 반영됐다

    def test_사용자가_중지를_답하면_한계_보고로_끝난다(self):
        ports = make_ports([FAIL_A, FAIL_B, PASS], InterruptUserGate())
        app = build_writer_graph(ports, checkpointer=MemorySaver())
        final = invoke_with_interrupts(
            app, initial_state(), "t2", lambda q: UserReply(action="stop")
        )
        assert final["status"] == "reported"


class _StubGate:
    def __init__(self, name: str, results: list[GateResult]):
        self.name = name
        self._results = results

    def check(self) -> GateResult:
        return self._results.pop(0)


class TestGenerateWithGates:
    def _run_writer(self, run_script):
        def run(state):
            ports = make_ports(list(run_script), InterruptUserGate())
            app = build_writer_graph(ports, checkpointer=MemorySaver())
            return invoke_with_interrupts(
                app, state, "gate-loop", lambda q: UserReply(action="continue")
            )

        return run

    def test_게이트_통과면_accepted다(self):
        gates = [_StubGate("assert", [GateResult("assert", True, "보존")])]
        result = generate_with_gates(
            run_writer=self._run_writer([PASS]),
            make_state=initial_state,
            make_gates=lambda: gates,
            base_instruction="지침",
            max_retries=3,
        )
        assert result.status == "accepted"
        assert result.attempts == 1

    def test_탈락_사유가_다음_지침서에_붙어_재시도된다(self):
        seen_instructions: list[str] = []

        def make_state(instruction):
            seen_instructions.append(instruction)
            return initial_state(instruction)

        gate_results = [
            GateResult("coverage", False, "분기 50% < 기준 70% (미실행 분기: [12])"),
            GateResult("coverage", True, "기준 충족"),
        ]
        result = generate_with_gates(
            run_writer=self._run_writer([PASS]),
            make_state=make_state,
            make_gates=lambda: [_StubGate("coverage", gate_results)],
            base_instruction="지침",
            max_retries=3,
        )
        assert result.status == "accepted"
        assert result.attempts == 2
        assert "미실행 분기: [12]" in seen_instructions[-1]  # 탈락 사유가 모델에게 돌아갔다

    def test_재시도를_소진하면_사람_확인_목록이다(self):
        always_fail = GateResult("assert", False, "기존 assert 훼손")
        result = generate_with_gates(
            run_writer=self._run_writer([PASS]),
            make_state=initial_state,
            make_gates=lambda: [_StubGate("assert", [always_fail, always_fail, always_fail])],
            base_instruction="지침",
            max_retries=3,
        )
        assert result.status == "human_review"
        assert result.attempts == 3
        assert "훼손" in result.gate_report.failure_reasons

    def test_에이전트가_한계_보고로_끝나면_게이트를_보지_않는다(self):
        blocked = RunResult(passed=False, summary="[샌드박스 시간 초과: 600초]")
        result = generate_with_gates(
            run_writer=self._run_writer([blocked]),
            make_state=initial_state,
            make_gates=lambda: [],
            base_instruction="지침",
            max_retries=3,
        )
        assert result.status == "not_passed"
        assert result.gate_report is None
