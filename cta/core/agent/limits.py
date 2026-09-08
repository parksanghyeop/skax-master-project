"""안전장치 미들웨어 — 반복 상한·실패 분류·내장 쓰기 도구 숨김 (ADR-0024 결정 4, ADR-0025).

왜 LLM을 안 쓰는가(R2): "몇 번 실행했나", "같은 실패가 반복되나", "환경 문제인가"는 전부
숫자 비교와 문자열 검사로 판정된다. 상한은 프롬프트 문장이 아니라 여기서 강제된다 — 모델이
아무리 원해도 `run_tests`가 실제로 돌지 않는다(v4 2.2 "사용자 허락 없이는 한도 초과 불가").
층: core — 도구 이름과 결과 문자열의 선두 표식만 안다. 메인·writer 서브에 **같은 인스턴스**를
넣는다(한 실행의 시도 수는 하나다).
"""

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

# 반복 상한 — 사용자 허락 없이 초과하지 않는다(v4 2.2). cta.toml [retry]로 조정(core/config.py).
ASK_EVERY_ATTEMPTS = 4  # 이 횟수 실패마다 사용자에게 묻는다 (v4 2.3 "한도 도달 → 멈추고 묻기")
MAX_TOTAL_ATTEMPTS = 8  # 하드 캡 — SC-001 5단계 "최대 8번"

# 실행 결과 문자열의 선두 표식. run_tests 도구의 출력 형식과 한 쌍이다.
PASSED_PREFIX = "통과"

# 실패 분류 결과 (v4 2.3의 갈림길). 전부 결정적 문자열 검사다(R2).
FAILURE_AUTO = "auto"  # 스스로 고칠 수 있는 실수 → 자동 재시도
FAILURE_ASK = "ask"  # 판단이 필요한 실패 → 멈추고 사용자에게
FAILURE_IMPOSSIBLE = "impossible"  # 통과 불가능이 명백 → 한계 보고

# 환경 문제 표식 — 재시도해도 소용없는 실패의 결정적 신호.
_IMPOSSIBLE_MARKERS = ("시간 초과", "실행 거부")

# 모델에게 보이지 않게 하는 하네스 내장 쓰기 도구(ADR-0025). 파일을 바꾸는 길은 write_test뿐이다.
HIDDEN_TOOLS = ("write_file", "edit_file", "delete")

# ask_user 도구 답의 선두 표식 — core/agent/tools.py와 한 쌍. 원장이 "중지"를 알아보는 결정적 신호.
REPLY_STOP_PREFIX = "사용자 답: 중지"


def classify_failure(last_run: str, prev_run: str) -> str:
    """실패의 성격을 분류한다 (v4 2.3 "어떤 실패인가?").

    세 가지 신호(환경 문제 표식, 같은 실패 반복, 그 외)는 문자열 비교로 판정된다.
    같은 실패가 두 번 반복되면 모델이 스스로 못 고치는 문제로 보고 사용자 판단을 구한다.
    """
    if any(marker in last_run for marker in _IMPOSSIBLE_MARKERS):
        return FAILURE_IMPOSSIBLE
    if prev_run and last_run == prev_run:
        return FAILURE_ASK
    return FAILURE_AUTO


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
    return str(name or "")


class HideWriteTools(AgentMiddleware):
    """모델에게 주는 도구 목록에서 내장 쓰기 도구를 뺀다 (ADR-0025 결정 2).

    permissions deny가 실제 실행을 막고, 이 미들웨어는 시도 자체(토큰·헛돌기)를 줄인다 — 두 겹.
    """

    name = "cta_hide_write_tools"

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        kept = [t for t in (request.tools or []) if _tool_name(t) not in HIDDEN_TOOLS]
        return handler(request.override(tools=kept))


class RunLedger(AgentMiddleware):
    """도구 호출 원장 — 시도 수를 세고 상한을 강제하며, 화면에 낼 회차 기록을 모은다.

    run_tests: 호출마다 attempts+1. 하드 캡·소프트 한도(질문 필요)·환경 문제·사용자 중지 상태에서는
      실행하지 않고 거부 문장을 돌려준다. 실행 뒤에는 결과에 결정적 안내(같은 실패 반복, 한도
      도달)를 덧붙여 모델이 다음 행동(진단·질문·한계 보고)을 고르게 한다.
    write_test / check_quality / report_finding / ask_user: 마지막 값을 기록만 한다.
    출력(속성): attempts, history[{attempt, write_result, run_result}], last_run, prev_run,
      last_code, last_write_result, quality, report — run_agent가 WriterState 모양으로 옮긴다.
    """

    name = "cta_run_ledger"

    def __init__(
        self,
        ask_every: int = ASK_EVERY_ATTEMPTS,
        max_total: int = MAX_TOTAL_ATTEMPTS,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        if ask_every < 1 or max_total < 1:
            raise ValueError(
                f"반복 상한은 1 이상이어야 한다: ask_every={ask_every}, max_total={max_total}"
            )
        self._ask_every = ask_every
        self._max_total = max_total
        self._progress = progress or (lambda _msg: None)
        self.attempts = 0
        self.history: list[dict] = []
        self.last_run = ""
        self.prev_run = ""
        self.last_code = ""
        self.last_write_result = ""
        self.quality = ""
        self.report = ""
        self.needs_ask = False  # 소프트 한도·같은 실패 반복 → ask_user 전에는 실행 거부
        self.blocked = ""  # "hard"(하드 캡) | "impossible"(환경 문제) | "stopped"(사용자 중지)

    def wrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolMessage | Command]
    ) -> ToolMessage | Command:
        call = request.tool_call
        name, args = call["name"], call.get("args") or {}
        if name == "task":
            self._progress(
                f"위임 → {args.get('subagent_type', '?')}: {str(args.get('description', ''))[:70]}"
            )
            return handler(request)
        if name == "write_test":
            self.last_code = str(args.get("code", ""))
            result = handler(request)
            self.last_write_result = _content(result)
            return result
        if name == "run_tests":
            return self._run_tests(request, handler)
        if name == "ask_user":
            result = handler(request)
            if _content(result).startswith(REPLY_STOP_PREFIX):
                self.blocked = "stopped"
            self.needs_ask = False
            return result
        if name == "check_quality":
            result = handler(request)
            self.quality = _content(result)
            return result
        if name == "report_finding":
            self.report = str(args.get("finding", ""))
            return handler(request)
        return handler(request)

    def _run_tests(self, request: ToolCallRequest, handler) -> ToolMessage | Command:
        refusal = self._refusal()
        if refusal:
            return _refuse(request, refusal)
        self.attempts += 1
        result = handler(request)
        outcome = _content(result)
        self.prev_run, self.last_run = self.last_run, outcome
        self.history.append(
            {
                "attempt": self.attempts,
                "write_result": self.last_write_result,
                "run_result": outcome,
            }
        )
        note = self._note_after_run(outcome)
        return _append(result, note) if note else result

    def _refusal(self) -> str:
        if self.blocked == "stopped":
            return "실행 거부: 사용자가 중지했다. report_finding으로 한계를 보고하고 끝내라."
        if self.blocked == "impossible":
            return (
                "실행 거부: 환경 문제로 통과가 불가능하다. "
                "report_finding으로 한계를 보고하고 끝내라."
            )
        if self.blocked == "hard" or self.attempts >= self._max_total:
            return (
                f"실행 거부: 실행 상한 {self._max_total}회에 도달했다. 더 실행할 수 없다 — "
                "report_finding으로 한계를 보고하고 끝내라."
            )
        if self.needs_ask:
            return (
                "실행 거부: 사용자에게 먼저 물어야 한다(소프트 한도 또는 같은 실패 반복). "
                "서브에이전트라면 지금까지의 결과를 보고하고 끝내고, 메인은 ask_user로 물어라."
            )
        return ""

    def _note_after_run(self, outcome: str) -> str:
        """실행 결과 뒤에 붙일 결정적 안내 — 통과면 없음."""
        if outcome.startswith(PASSED_PREFIX):
            return ""
        failure = classify_failure(outcome, self.prev_run)
        if failure == FAILURE_IMPOSSIBLE:
            self.blocked = "impossible"
            return (
                "[안내] 통과 불가능이 명백하다(환경 문제). "
                "더 시도하지 말고 report_finding으로 끝내라."
            )
        if self.attempts >= self._max_total:
            self.blocked = "hard"
            return (
                f"[안내] 실행 상한 {self._max_total}회에 도달했다. 더 시도할 수 없다 — "
                "report_finding으로 한계를 보고하라."
            )
        if failure == FAILURE_ASK:
            self.needs_ask = True
            return (
                "[안내] 직전과 같은 실패가 반복됐다 — 스스로 못 고치는 문제일 수 있다. "
                "서브에이전트라면 여기서 보고하고 끝내라. "
                "메인은 diagnoser에게 원인 분석을 맡기거나 ask_user로 사용자에게 물어라."
            )
        if self.attempts % self._ask_every == 0:
            self.needs_ask = True
            return (
                f"[안내] {self.attempts}회 실패 — 소프트 한도다. "
                "다음 실행 전에 사용자 확인이 필요하다. "
                "서브에이전트라면 여기서 보고하고 끝내라. 메인은 ask_user로 물어라."
            )
        return ""


def _content(result: ToolMessage | Command) -> str:
    if isinstance(result, ToolMessage):
        return result.content if isinstance(result.content, str) else str(result.content)
    return ""


def _refuse(request: ToolCallRequest, message: str) -> ToolMessage:
    return ToolMessage(
        content=message, tool_call_id=request.tool_call["id"], name=request.tool_call["name"]
    )


def _append(result: ToolMessage | Command, note: str) -> ToolMessage | Command:
    if not isinstance(result, ToolMessage):
        return result
    return ToolMessage(
        content=f"{_content(result)}\n\n{note}", tool_call_id=result.tool_call_id, name=result.name
    )
