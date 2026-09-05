"""테스트 작성 서브그래프(core/writer_graph)의 단위 테스트 — 전부 Fake로 돈다.

검증하는 흐름(v4 2.3): 첫 시도 통과 / 실패 후 재시도 끝 통과 / 소프트 한도에서
사용자에게 묻기(자동 계속 스텁) / 하드 한도에서 한계 보고 / 사용자 중지.
"""

from cta.adapters.fake import (
    FakeCodeGraph,
    FakeQualityChecker,
    FakeSourceInspector,
    FakeTestWriter,
    ScriptedGenerator,
    ScriptedTestRunner,
    ScriptedUserGate,
)
from cta.core.ports import RunResult, UserReply
from cta.core.writer_graph import (
    ASK_EVERY_ATTEMPTS,
    MAX_TOTAL_ATTEMPTS,
    WriterPorts,
    build_writer_graph,
)

PASS = RunResult(passed=True, summary="Tests run: 2, Failures: 0")
FAIL = RunResult(passed=False, summary="[ERROR] expected 3 but was 4")


def distinct_fails(n: int) -> list[RunResult]:
    """서로 다른 실패 n개 — '같은 실패 반복' 분류에 걸리지 않는 자동 재시도 시나리오용."""
    return [RunResult(passed=False, summary=f"[ERROR] 실패 유형 {i}") for i in range(n)]


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
        "prev_run": "",
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

    def test_진행_상황이_콜백으로_보고된다(self):
        # 긴 단계(LLM 호출·샌드박스 실행)가 무음이면 사용자가 멈춘 줄 안다 — 실시간 보고
        messages: list[str] = []
        ports = make_ports([FAIL, PASS])
        ports.progress = messages.append
        build_writer_graph(ports).invoke(initial_state())
        text = "\n".join(messages)
        assert "정보 수집" in text
        assert "코드 생성 중" in text and "2번째 시도" in text  # 재시도도 보인다
        assert "샌드박스 실행 중" in text

    def test_progress_기본값은_무음이라_기존_호출부가_그대로_돈다(self):
        final = build_writer_graph(make_ports([PASS])).invoke(initial_state())
        assert final["status"] == "passed"

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
        ports = make_ports(distinct_fails(MAX_TOTAL_ATTEMPTS), gate)
        final = build_writer_graph(ports).invoke(initial_state())
        # 3회째 실패에서 한 번 물었고(자동 계속), 6회째는 묻지 않고 하드 캡으로 끝났다
        assert len(gate.questions) == 1
        assert final["status"] == "reported"
        assert final["attempts"] == MAX_TOTAL_ATTEMPTS
        assert final["report"].startswith("한계 보고")

    def test_사용자가_중지하면_한계_보고로_정상_종료한다(self):
        gate = ScriptedUserGate([UserReply(action="stop")])
        ports = make_ports(distinct_fails(10), gate)
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "reported"
        assert final["attempts"] == ASK_EVERY_ATTEMPTS  # 첫 질문 시점에 멈췄다

    def test_사용자_힌트는_다음_시도의_재료에_들어간다(self):
        gate = ScriptedUserGate([UserReply(action="continue", hint="0 나누기를 먼저 시험하라")])
        ports = make_ports(distinct_fails(ASK_EVERY_ATTEMPTS) + [PASS], gate)
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "passed"
        assert "0 나누기를 먼저 시험하라" in final["context"]


class TestFailureClassification:
    """실패 분류(M6, v4 2.3) — 자동 수정 가능 / 판단 필요 / 불가능."""

    def test_같은_실패가_반복되면_한도_전에_묻는다(self):
        gate = ScriptedUserGate([UserReply(action="stop")])
        ports = make_ports([FAIL, FAIL], gate)  # 동일한 실패 두 번 = 판단 필요
        final = build_writer_graph(ports).invoke(initial_state())
        assert len(gate.questions) == 1
        assert final["attempts"] == 2  # 소프트 한도(3) 전에 물었다
        assert final["status"] == "reported"

    def test_환경_문제는_묻지_않고_한계_보고한다(self):
        blocked = RunResult(passed=False, summary="[샌드박스 시간 초과: 600초]")
        gate = ScriptedUserGate()
        ports = make_ports([blocked], gate)
        final = build_writer_graph(ports).invoke(initial_state())
        assert final["status"] == "reported"
        assert final["attempts"] == 1  # 재시도해도 소용없는 실패는 즉시 끝낸다
        assert gate.questions == []


class TestConfigurableLimits:
    """반복 상한은 cta.toml [retry]로 조정된다 — build_writer_graph 인자로 들어온다 (3단계 A-2)."""

    def test_max_total을_줄이면_그_횟수에서_한계_보고한다(self):
        ports = make_ports(distinct_fails(5))
        final = build_writer_graph(ports, max_total=2).invoke(initial_state())
        assert final["status"] == "reported"
        assert final["attempts"] == 2

    def test_ask_every를_줄이면_더_일찍_묻는다(self):
        gate = ScriptedUserGate([UserReply(action="stop")])
        ports = make_ports(distinct_fails(5), gate)
        final = build_writer_graph(ports, ask_every=1).invoke(initial_state())
        assert final["attempts"] == 1 and len(gate.questions) == 1

    def test_상한이_1_미만이면_조립_시점에_거부한다(self):
        import pytest

        with pytest.raises(ValueError):
            build_writer_graph(make_ports([PASS]), max_total=0)


class TestPromptDoesNotAccumulate:
    """대화 압축이 필요 없는 이유(ADR-0016): 매 시도의 프롬프트에는 직전 실패 하나만 들어간다."""

    def test_세_번째_시도의_실패_재료는_직전_실패_하나뿐이다(self):
        ports = make_ports(distinct_fails(2) + [PASS])
        build_writer_graph(ports).invoke(initial_state())
        calls = ports.generator.calls
        assert len(calls) == 3
        assert "실패 유형 1" in calls[2]["last_failure"]
        assert "실패 유형 0" not in calls[2]["last_failure"]  # 옛 실패는 누적되지 않는다
