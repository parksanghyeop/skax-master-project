"""게이트 재시도 루프 — 생성 → 검문소 → 탈락 사유 반환 → 재시도 (M6, v4 2.4).

테스트를 만든 에이전트는 합격 판정에 관여하지 못한다: 생성이 끝난 뒤 게이트가
기계적으로 판정하고, 탈락하면 **사유를 문장으로 모델에게 돌려주고** 다시 시킨다.
설정된 횟수(기본 3회)를 넘기면 자동 반영하지 않고 사람 확인 목록으로 보낸다.
층: core — 게이트 목록은 호출부(언어를 아는 쪽)가 팩토리로 넘긴다.
"""

from collections.abc import Callable
from dataclasses import dataclass

from cta.core.gates import Gate, GateReport, run_gates
from cta.core.writer_graph import WriterState


@dataclass(frozen=True)
class SubmitResult:
    """게이트 루프의 최종 결과.

    status: "accepted"(게이트 통과) | "human_review"(재시도 소진·사람 확인 필요)
            | "not_passed"(에이전트가 테스트를 통과시키지 못함 — 한계 보고 포함)
    """

    status: str
    final_state: WriterState
    gate_report: GateReport | None
    attempts: int  # 게이트까지 간 시도 수 (에이전트 내부 재시도와 별개)


def generate_with_gates(
    run_writer: Callable[[WriterState], WriterState],
    make_state: Callable[[str], WriterState],
    make_gates: Callable[[], list[Gate]],
    base_instruction: str,
    max_retries: int,
) -> SubmitResult:
    """생성→게이트를 최대 max_retries회 돌린다.

    입력: run_writer — 상태를 받아 작성 그래프를 끝까지 돌리는 함수,
      make_state — 지침서로 초기 상태를 만드는 함수,
      make_gates — 게이트 목록 팩토리(호출 시점마다 새로 검사),
      base_instruction — 원래 작업 지침서.
    """
    instruction = base_instruction
    last_report: GateReport | None = None
    final_state: WriterState = make_state(instruction)
    for attempt in range(1, max_retries + 1):
        final_state = run_writer(make_state(instruction))
        if final_state["status"] != "passed":
            # 에이전트 스스로 한계 보고로 끝냄 — 게이트를 볼 것도 없다
            return SubmitResult("not_passed", final_state, None, attempt)
        last_report = run_gates(make_gates())
        if last_report.passed:
            return SubmitResult("accepted", final_state, last_report, attempt)
        # 탈락 사유를 다음 지침서에 그대로 붙인다 (v4 2.4 "탈락했을 때")
        instruction = (
            f"{base_instruction}\n\n[품질 검사 탈락 — 아래 사유를 해소하라 "
            f"(시도 {attempt}/{max_retries})]\n{last_report.failure_reasons}"
        )
    return SubmitResult("human_review", final_state, last_report, max_retries)
