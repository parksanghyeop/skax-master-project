"""테스트 작성 서브그래프 — v4 2.3의 반복 흐름을 LangGraph로 조립.

흐름: 정보 수집 → 코드 생성·쓰기 → 실행 → 통과면 품질 확인, 실패면 한도 안
재시도. 소프트 한도에 닿으면 사용자에게 묻고(⏸ PoC는 자동 "계속" 스텁),
하드 한도·중지 답변이면 한계 보고로 정상 종료 — 출구는 둘 다 정상이다.
왜 그래프인가: 멈췄다 이어 하기(2단계의 interrupt 실연결)를 같은 장치로 쓰기
위해서다(v4 2.2). 각 노드 함수는 그래프 없이 단독 호출·테스트할 수 있다.
층: core — 포트만 알고 대상 언어를 모른다(R1). LLM은 generator 포트 뒤에만 있다(R2).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from cta.core.ports import (
    CodeGraph,
    QualityChecker,
    SourceInspector,
    TestCodeGenerator,
    TestRunner,
    TestWriter,
    UserGate,
    UserReply,
)
from cta.core.tools import (
    check_quality,
    inspect_target,
    query_code_graph,
    report_finding,
    run_tests,
    write_test,
)
from cta.core.tools.query_code_graph import QUERY_SIMILAR_TESTS

# 반복 상한 — 그래프 상태의 숫자로 관리하고 사용자 허락 없이 초과하지 않는다(v4 2.2).
ASK_EVERY_ATTEMPTS = 4  # 이 횟수 실패마다 사용자에게 묻는다 (v4 2.3 "한도 도달 → 멈추고 묻기")
MAX_TOTAL_ATTEMPTS = 8  # 하드 캡 — SC-001 5단계 "최대 8번". 자동 "계속"의 무한 루프 방지

# 실행 결과 문자열의 선두 표식. run_tests 도구의 출력 형식과 한 쌍이다.
_PASSED_PREFIX = "통과"

# 실패 분류 결과 (v4 2.3의 갈림길). 전부 결정적 문자열 검사다(R2).
FAILURE_AUTO = "auto"  # 스스로 고칠 수 있는 실수 → 자동 재시도
FAILURE_ASK = "ask"  # 판단이 필요한 실패 → 멈추고 사용자에게
FAILURE_IMPOSSIBLE = "impossible"  # 통과 불가능이 명백 → 한계 보고

# 환경 문제 표식 — 재시도해도 소용없는 실패의 결정적 신호.
_IMPOSSIBLE_MARKERS = ("시간 초과", "실행 거부")


def classify_failure(last_run: str, prev_run: str) -> str:
    """실패의 성격을 분류한다 (v4 2.3 "어떤 실패인가?").

    왜 LLM을 안 쓰나(R2): 세 가지 신호(환경 문제 표식, 같은 실패 반복, 그 외)는
    문자열 비교로 판정된다. 같은 실패가 두 번 반복되면 모델이 스스로 못 고치는
    문제로 보고 사용자 판단을 구한다.
    """
    if any(marker in last_run for marker in _IMPOSSIBLE_MARKERS):
        return FAILURE_IMPOSSIBLE
    if prev_run and last_run == prev_run:
        return FAILURE_ASK
    return FAILURE_AUTO


class WriterState(TypedDict):
    """서브그래프의 상태. 앞 단계(조치 결정)가 instruction~selector를 채워 넘긴다."""

    instruction: str  # 작업 지침서 (v4 2단계 Step 2-B)
    target: str  # 대상 메서드 식별자
    test_path: str  # 테스트를 쓸 파일 경로
    selector: str  # 실행 selector
    context: str  # 수집된 정보 (대상 조사 + 비슷한 테스트)
    test_code: str  # 현재 시도의 테스트 코드
    write_result: str  # 마지막 쓰기(컴파일 검사) 결과
    last_run: str  # 마지막 실행 결과
    prev_run: str  # 직전 시도의 실행 결과 — 같은 실패 반복(판단 필요) 감지용
    attempts: int  # 시도 횟수 — 상한 검사의 근거
    quality: str  # 품질 확인 결과
    report: str  # 한계 보고 내용
    status: str  # working | passed | reported
    # 아래 둘은 선택 항목 — 옛 호출부(초기 상태에 키 없음)와 호환되게 .get으로 읽는다.
    extra_context: str  # 호출부가 미리 모아 준 재료(확인 항목·객체 생성법·기존 테스트)
    history: list  # 시도별 기록 [{"attempt", "write_result", "run_result"}] — 회차 요약 출력용


@dataclass
class WriterPorts:
    """서브그래프가 쓰는 포트 묶음. 실물(어댑터·LLM)과 Fake를 통째로 갈아끼운다."""

    inspector: SourceInspector
    graph: CodeGraph
    writer: TestWriter
    runner: TestRunner
    checker: QualityChecker
    gate: UserGate
    generator: TestCodeGenerator
    # 진행 상황 보고 콜백 — LLM 호출·샌드박스 실행처럼 수십 초 걸리는 단계를
    # 사용자가 볼 수 있게 한다. 기본은 무음(테스트·재생 호환). 층 규칙: 메시지는
    # 언어 중립 문구만 담는다(R1) — 출력 형식(경과 시간 등)은 CLI 몫이다.
    progress: Callable[[str], None] = field(default=lambda _msg: None)


def gather_context(inspector: SourceInspector, graph: CodeGraph, target: str) -> str:
    """정보 수집 결과를 하나의 문자열로 조립한다.

    모듈 함수로 분리한 이유: 호출 기록 생성 스크립트가 그래프와 정확히 같은
    프롬프트 재료를 만들어야 재생이 어긋나지 않는다(replay 요청 대조).
    """
    found = inspect_target(inspector, target)
    similar = query_code_graph(graph, QUERY_SIMILAR_TESTS, target)
    return f"[대상 조사]\n{found}\n\n[비슷한 모양의 기존 테스트]\n{similar}"


class InterruptUserGate:
    """LangGraph interrupt로 실제 사용자에게 묻는 UserGate 구현 (M6 실연결).

    ask가 호출되는 순간 그래프가 그 자리에서 **정지**하고 상태가 저장된다.
    invoke_with_interrupts(아래)가 질문을 밖으로 전달하고, 사용자의 답으로
    같은 지점부터 재개한다 — 답이 늦게 와도 손실이 없다(v4 2.3).
    checkpointer가 있는 그래프 안에서만 동작한다.
    """

    def ask(self, question: str) -> UserReply:
        payload = interrupt({"question": question})
        # 재개 시 interrupt()가 사용자의 답(payload)을 그대로 돌려준다
        return UserReply(
            action=str(payload.get("action", "continue")),
            hint=str(payload.get("hint", "")),
        )


def invoke_with_interrupts(
    app,
    initial_state: WriterState,
    thread_id: str,
    ask_user: Callable[[str], UserReply],
) -> WriterState:
    """그래프를 실행하되, 중단(interrupt)이 오면 ask_user로 답을 받아 재개한다.

    입력: app — checkpointer와 함께 컴파일된 그래프, thread_id — 재개용 식별자,
      ask_user — 질문 문자열을 받아 UserReply를 돌려주는 콜백(CLI는 stdin 입력).
    출력: 최종 상태. 중단이 없으면 한 번의 invoke와 같다.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke(initial_state, config)
    while "__interrupt__" in result:
        question = result["__interrupt__"][0].value["question"]
        reply = ask_user(question)
        result = app.invoke(Command(resume={"action": reply.action, "hint": reply.hint}), config)
    return result


def build_writer_graph(
    ports: WriterPorts,
    checkpointer=None,
    ask_every: int = ASK_EVERY_ATTEMPTS,
    max_total: int = MAX_TOTAL_ATTEMPTS,
):
    """포트를 닫아 넣은(클로저) 노드들로 서브그래프를 조립해 컴파일한다.

    출력: invoke(초기 상태)로 실행 가능한 LangGraph 앱.
    checkpointer: InterruptUserGate(실사용자 개입)를 쓰려면 필수 — 정지 지점의
      상태 저장·재개가 여기 담긴다. 없으면 스텁 게이트 전용(테스트·재생).
    ask_every / max_total: 반복 상한. 기본값은 v4 그대로이고 cta.toml [retry]로
      조정한다(core/config.py) — 상한은 사용자 허락 없이 넘지 않는다(v4 2.2).
    """
    if ask_every < 1 or max_total < 1:
        raise ValueError(
            f"반복 상한은 1 이상이어야 한다: ask_every={ask_every}, max_total={max_total}"
        )

    def gather(state: WriterState) -> dict:
        ports.progress("정보 수집 — 대상 조사·비슷한 테스트 검색")
        context = gather_context(ports.inspector, ports.graph, state["target"])
        extra = state.get("extra_context") or ""
        if extra:
            context = f"{context}\n\n{extra}"
        return {"context": context}

    def write(state: WriterState) -> dict:
        attempt = state.get("attempts", 0) + 1
        ports.progress(f"코드 생성 중 — LLM 호출 ({attempt}번째 시도, 수십 초 걸릴 수 있다)")
        started = time.monotonic()
        code = ports.generator.generate(
            state["instruction"],
            state["context"],
            state.get("test_code", ""),
            state.get("last_run", ""),
        )
        ports.progress(f"생성 완료 ({len(code)}자, {time.monotonic() - started:.0f}초) → 파일 쓰기")
        result = write_test(ports.writer, state["test_path"], code)
        return {
            "test_code": code,
            "write_result": result,
            "attempts": attempt,
        }

    def run(state: WriterState) -> dict:
        ports.progress(f"샌드박스 실행 중 — {state['selector']}")
        started = time.monotonic()
        outcome = run_tests(ports.runner, state["selector"])
        first_line = outcome.splitlines()[0] if outcome else ""
        ports.progress(f"실행 끝 ({time.monotonic() - started:.0f}초) — {first_line}")
        # 회차 기록: 상태 갱신은 덮어쓰기라 기존 목록에 항목을 더한 새 목록을 돌려준다
        entry = {
            "attempt": state.get("attempts", 0),
            "write_result": state.get("write_result", ""),
            "run_result": outcome,
        }
        return {
            "last_run": outcome,
            "prev_run": state.get("last_run", ""),
            "history": list(state.get("history") or []) + [entry],
        }

    def route_after_run(state: WriterState) -> str:
        if state["last_run"].startswith(_PASSED_PREFIX):
            return "quality"
        failure = classify_failure(state["last_run"], state.get("prev_run", ""))
        if failure == FAILURE_IMPOSSIBLE:
            return "report"  # 통과 불가능이 명백 → 한계 보고 (v4 2.3)
        if state["attempts"] >= max_total:
            return "report"  # 하드 캡 — 게이트가 계속을 반복해도 여기서 끝난다
        if failure == FAILURE_ASK or state["attempts"] % ask_every == 0:
            return "ask"  # 판단 필요(같은 실패 반복) 또는 소프트 한도 도달
        return "write"

    def ask(state: WriterState) -> dict:
        # ⏸ 멈춤 지점(v4 2.3). 실사용은 InterruptUserGate(그래프 정지→재개),
        # 테스트·재생은 대본 게이트 — 같은 노드 경계에 구현만 갈아 끼운다.
        reply = ports.gate.ask(
            f"{state['attempts']}회 실패했다. 마지막 실패:\n{state['last_run']}\n계속할까?"
        )
        if reply.action == "stop":
            return {"status": "stopping"}
        extra = f"\n\n[사용자 힌트]\n{reply.hint}" if reply.hint else ""
        return {"status": "working", "context": state["context"] + extra}

    def route_after_ask(state: WriterState) -> str:
        return "report" if state["status"] == "stopping" else "write"

    def quality(state: WriterState) -> dict:
        return {"quality": check_quality(ports.checker, state["test_path"]), "status": "passed"}

    def report(state: WriterState) -> dict:
        finding = (
            f"대상 {state['target']}의 테스트를 통과시키지 못했다 "
            f"(시도 {state['attempts']}회).\n마지막 실패:\n{state['last_run']}"
        )
        return {"report": report_finding(finding), "status": "reported"}

    graph = StateGraph(WriterState)
    graph.add_node("gather", gather)
    graph.add_node("write", write)
    graph.add_node("run", run)
    graph.add_node("ask", ask)
    graph.add_node("quality", quality)
    graph.add_node("report", report)

    graph.add_edge(START, "gather")
    graph.add_edge("gather", "write")
    graph.add_edge("write", "run")
    graph.add_conditional_edges(
        "run",
        route_after_run,
        {"quality": "quality", "write": "write", "ask": "ask", "report": "report"},
    )
    graph.add_conditional_edges("ask", route_after_ask, {"write": "write", "report": "report"})
    graph.add_edge("quality", END)
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
