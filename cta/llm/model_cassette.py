"""LangChain 모델 호출의 record & replay — 카세트 v2 미들웨어 (ADR-0024 결정 5).

`replay.py`(v1, 텍스트 chat 한 번)와 같은 원칙을 도구 호출형 멀티턴에 적용한다:
녹음은 모델 호출마다 (요청 키, 응답 메시지)를 파일에 누적하고, 재생은 파일만으로 응답한다.
요청 키는 deployment + 시스템 프롬프트 + 정규화한 메시지(역할·내용·tool_calls) + 도구 이름 —
메시지 id처럼 실행마다 달라지는 값은 뺀다. 대조는 완전 일치다("비슷하면 통과" 없음).
층: llm — 모든 모델 호출이 이 미들웨어를 지나야 재생이 성립한다(R7). 메인·서브에이전트
모두에 **같은 인스턴스**를 넣는다(한 실행 = 카세트 하나, 호출 순서 = 기록 순서).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, message_to_dict, messages_from_dict

from cta.llm.replay import CassetteError

CASSETTE_VERSION = 2  # v1(replay.py)과 구분 — 형식이 다르므로 섞어 읽지 않는다


def model_label(model: Any) -> str:
    """요청 키에 넣을 모델 이름 — deployment 이름이 곧 모델이다(ADR-0011)."""
    for attr in ("deployment_name", "model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__


def _text(content: Any) -> str:
    """메시지 내용을 문자열로 — 블록 목록(멀티모달·캐시 표식)은 JSON으로 고정 표기."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def normalize_message(message: BaseMessage) -> dict:
    """대조용 표현 — 실행마다 바뀌는 id·메타데이터를 뺀 역할·내용·도구 호출만."""
    entry: dict[str, Any] = {"type": message.type, "content": _text(message.content)}
    if isinstance(message, AIMessage) and message.tool_calls:
        entry["tool_calls"] = [
            {"name": tc["name"], "args": tc["args"], "id": tc.get("id")}
            for tc in message.tool_calls
        ]
    if message.type == "tool":
        entry["tool_call_id"] = getattr(message, "tool_call_id", None)
        entry["name"] = getattr(message, "name", None)
    return entry


def _tool_names(tools: Any) -> list[str]:
    names = []
    for t in tools or []:
        name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
        if name:
            names.append(str(name))
    return sorted(names)


def request_key(request: ModelRequest) -> dict:
    """녹음·재생이 대조할 요청의 표준 표현. 시크릿은 애초에 담기지 않는다."""
    system = request.system_message
    return {
        "model": model_label(request.model),
        "system": _text(system.content) if system is not None else "",
        "messages": [normalize_message(m) for m in request.messages],
        "tools": _tool_names(request.tools),
    }


def _result_messages(response: Any) -> list[BaseMessage]:
    """handler 반환은 ModelResponse(result 목록) 또는 AIMessage 하나 — 둘 다 목록으로."""
    if isinstance(response, BaseMessage):
        return [response]
    return list(response.result)


def _serialize(messages: list[BaseMessage]) -> list[dict]:
    return [message_to_dict(m) for m in messages]


class RecordingModelMiddleware(AgentMiddleware):
    """실호출을 그대로 통과시키며 (요청 키, 응답)을 카세트에 누적 저장한다.

    호출마다 파일을 다시 쓴다 — 도중에 죽어도 그때까지의 기록은 남는다.
    """

    name = "cta_model_recording"

    def __init__(self, cassette_path: str | Path) -> None:
        super().__init__()
        self._path = Path(cassette_path)
        self._entries: list[dict] = []

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        response = handler(request)
        self._entries.append(
            {"request": request_key(request), "response": _serialize(_result_messages(response))}
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"version": CASSETTE_VERSION, "entries": self._entries},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return response


class ReplayModelMiddleware(AgentMiddleware):
    """카세트만으로 응답한다 — handler(실제 모델)를 아예 부르지 않는다.

    실패 시 동작: 파일 없음·버전 다름·기록 소진·요청 불일치 → CassetteError(R7: 폴백 없음).
    재생 모델은 `NoCallChatModel(deployment_name=replay.deployment)`로 만든다 —
    모델 이름이 키에 든다.
    """

    name = "cta_model_replay"

    def __init__(self, cassette_path: str | Path) -> None:
        super().__init__()
        self._path = Path(cassette_path)
        if not self._path.is_file():
            raise CassetteError(
                f"카세트 없음: {self._path} — 재생 모드는 실호출로 폴백하지 않는다(R7)"
            )
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != CASSETTE_VERSION:
            raise CassetteError(
                f"카세트 형식이 v{CASSETTE_VERSION}가 아니다: {self._path} — 기록을 다시 만든다"
            )
        self._entries: list[dict] = data["entries"]
        self._cursor = 0
        # 기록 당시의 deployment — 재생 모델(NoCallChatModel)이 같은 이름을 달아야 키가 맞는다
        self.deployment: str = self._entries[0]["request"]["model"] if self._entries else "replay"

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        if self._cursor >= len(self._entries):
            raise CassetteError(
                f"카세트 소진: {self._path} — 기록된 호출 수({len(self._entries)})를 넘었다"
            )
        entry = self._entries[self._cursor]
        actual = request_key(request)
        if entry["request"] != actual:
            raise CassetteError(
                f"카세트 요청 불일치 (호출 #{self._cursor}): {self._path}\n"
                f"어긋난 항목: {_first_difference(entry['request'], actual)}"
            )
        self._cursor += 1
        return ModelResponse(result=messages_from_dict(entry["response"]), structured_response=None)


def _first_difference(expected: dict, actual: dict) -> str:
    """불일치 원인을 짧게 — 디버깅용. 메시지 본문 전체를 쏟아내지 않는다."""
    for key in ("model", "tools", "system"):
        if expected.get(key) != actual.get(key):
            return (
                f"{key} (기록 {str(expected.get(key))[:80]!r} / 실제 {str(actual.get(key))[:80]!r})"
            )
    exp_msgs, act_msgs = expected.get("messages", []), actual.get("messages", [])
    if len(exp_msgs) != len(act_msgs):
        return f"messages 길이 (기록 {len(exp_msgs)} / 실제 {len(act_msgs)})"
    for i, (e, a) in enumerate(zip(exp_msgs, act_msgs, strict=True)):
        if e != a:
            return (
                f"messages[{i}] ({e.get('type')}: {str(e.get('content'))[:80]!r} / "
                f"{str(a.get('content'))[:80]!r})"
            )
    return "알 수 없음"
