"""테스트 작성 서브그래프 — v4 2.3의 반복 흐름을 LangGraph로 조립.

흐름: 정보 수집 → 코드 생성·쓰기 → 실행 → 통과면 품질 확인, 실패면 한도 안
재시도. 소프트 한도에 닿으면 사용자에게 묻고(⏸ PoC는 자동 "계속" 스텁),
하드 한도·중지 답변이면 한계 보고로 정상 종료 — 출구는 둘 다 정상이다.
왜 그래프인가: 멈췄다 이어 하기(2단계의 interrupt 실연결)를 같은 장치로 쓰기
위해서다(v4 2.2). 각 노드 함수는 그래프 없이 단독 호출·테스트할 수 있다.
층: core — 포트만 알고 대상 언어를 모른다(R1). LLM은 generator 포트 뒤에만 있다(R2).
"""

from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from core.ports import (
    CodeGraph,
    QualityChecker,
    SourceInspector,
    TestCodeGenerator,
    TestRunner,
    TestWriter,
    UserGate,
)
from core.tools import (
    check_quality,
    inspect_target,
    query_code_graph,
    report_finding,
    run_tests,
    write_test,
)
from core.tools.query_code_graph import QUERY_SIMILAR_TESTS

# 반복 상한 — 그래프 상태의 숫자로 관리하고 사용자 허락 없이 초과하지 않는다(v4 2.2).
ASK_EVERY_ATTEMPTS = 3  # 이 횟수 실패마다 사용자에게 묻는다 (v4 2.3 "한도 도달 → 멈추고 묻기")
MAX_TOTAL_ATTEMPTS = 6  # PoC 하드 캡 — 자동 "계속" 스텁이 무한 루프가 되지 않게 하는 안전망

# 실행 결과 문자열의 선두 표식. run_tests 도구의 출력 형식과 한 쌍이다.
_PASSED_PREFIX = "통과"


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
    attempts: int  # 시도 횟수 — 상한 검사의 근거
    quality: str  # 품질 확인 결과
    report: str  # 한계 보고 내용
    status: str  # working | passed | reported


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


def gather_context(inspector: SourceInspector, graph: CodeGraph, target: str) -> str:
    """정보 수집 결과를 하나의 문자열로 조립한다.

    모듈 함수로 분리한 이유: 호출 기록 생성 스크립트가 그래프와 정확히 같은
    프롬프트 재료를 만들어야 재생이 어긋나지 않는다(replay 요청 대조).
    """
    found = inspect_target(inspector, target)
    similar = query_code_graph(graph, QUERY_SIMILAR_TESTS, target)
    return f"[대상 조사]\n{found}\n\n[비슷한 모양의 기존 테스트]\n{similar}"


def build_writer_graph(ports: WriterPorts):
    """포트를 닫아 넣은(클로저) 노드들로 서브그래프를 조립해 컴파일한다.

    출력: invoke(초기 상태)로 실행 가능한 LangGraph 앱.
    """

    def gather(state: WriterState) -> dict:
        return {"context": gather_context(ports.inspector, ports.graph, state["target"])}

    def write(state: WriterState) -> dict:
        code = ports.generator.generate(
            state["instruction"],
            state["context"],
            state.get("test_code", ""),
            state.get("last_run", ""),
        )
        result = write_test(ports.writer, state["test_path"], code)
        return {
            "test_code": code,
            "write_result": result,
            "attempts": state.get("attempts", 0) + 1,
        }

    def run(state: WriterState) -> dict:
        return {"last_run": run_tests(ports.runner, state["selector"])}

    def route_after_run(state: WriterState) -> str:
        if state["last_run"].startswith(_PASSED_PREFIX):
            return "quality"
        if state["attempts"] >= MAX_TOTAL_ATTEMPTS:
            return "report"  # 하드 캡 — 스텁 게이트가 계속을 반복해도 여기서 끝난다
        if state["attempts"] % ASK_EVERY_ATTEMPTS == 0:
            return "ask"
        return "write"

    def ask(state: WriterState) -> dict:
        # ⏸ 멈춤 지점 골격(v4 2.3). 2단계에서 langgraph interrupt로 실연결하고,
        # PoC에서는 UserGate 스텁이 즉시 답한다 — 노드 경계를 지금 만들어 두는
        # 이유는 나중에 노드 재배선 없이 안쪽만 바꾸기 위해서다.
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
    return graph.compile()
