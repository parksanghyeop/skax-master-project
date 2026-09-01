"""LLM 호출의 record & replay — 카세트(요청·응답 기록 파일) 장치.

왜 필요한가: LLM이 낀 프로그램을 보통 프로그램처럼 자동 테스트하기 위해서다
(v4 6.4). 녹음(record)은 실제 클라이언트를 감싸 요청·응답을 파일에 남기고,
재생(replay)은 파일만으로 응답한다 — 결과가 매번 같고 비용이 0이다.
층: llm — 모든 호출이 여기를 경유해야 이 장치가 작동한다(R7).
"""

import json
from dataclasses import asdict
from pathlib import Path

from llm.client import ChatMessage, ChatResponse, LlmClient


class CassetteError(RuntimeError):
    """재생이 불가능한 상황 — 카세트 없음·소진·요청 불일치.

    왜 실패로 처리하나: 재생 모드에서 몰래 실제 LLM을 호출하는 폴백은 금지다
    (절대 규칙 R7). 카세트가 어긋나면 테스트가 깨져야 개발자가 다시 녹음한다.
    """


def _request_key(messages: list[ChatMessage], model: str) -> dict:
    """녹음·재생이 대조할 요청의 표준 표현. 토큰 등 시크릿은 애초에 담지 않는다."""
    return {"model": model, "messages": [asdict(m) for m in messages]}


class RecordingClient:
    """실제 클라이언트를 감싸 요청·응답을 카세트에 누적 저장한다.

    입력: inner 실제 호출을 수행할 클라이언트, cassette_path 저장 위치(JSON).
    호출할 때마다 파일을 다시 쓴다 — 도중에 죽어도 그때까지의 기록은 남는다.
    """

    def __init__(self, inner: LlmClient, cassette_path: str | Path) -> None:
        self._inner = inner
        self._path = Path(cassette_path)
        self._entries: list[dict] = []

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        response = self._inner.chat(messages, model)
        self._entries.append(
            {"request": _request_key(messages, model), "response": {"content": response.content}}
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return response


class ReplayClient:
    """카세트만으로 응답한다 — 실제 호출 능력이 아예 없다.

    재생은 녹음과 같은 순서로 진행되며, 매 호출마다 기록된 요청과 실제 요청을
    대조한다. 어긋나면 CassetteError — "비슷하면 통과"는 없다(결정성 보장).
    실패 시 동작: 카세트 파일 없음·기록 소진·요청 불일치 → CassetteError.
    """

    def __init__(self, cassette_path: str | Path) -> None:
        self._path = Path(cassette_path)
        if not self._path.is_file():
            raise CassetteError(
                f"카세트 없음: {self._path} — 재생 모드는 실호출로 폴백하지 않는다(R7)"
            )
        self._entries: list[dict] = json.loads(self._path.read_text(encoding="utf-8"))
        self._cursor = 0

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        if self._cursor >= len(self._entries):
            raise CassetteError(f"카세트 소진: {self._path} — 기록된 호출 수를 넘었다")
        entry = self._entries[self._cursor]
        actual = _request_key(messages, model)
        if entry["request"] != actual:
            raise CassetteError(
                f"카세트 요청 불일치 (호출 #{self._cursor}): "
                f"기록={json.dumps(entry['request'], ensure_ascii=False)[:200]} / "
                f"실제={json.dumps(actual, ensure_ascii=False)[:200]}"
            )
        self._cursor += 1
        return ChatResponse(content=entry["response"]["content"])
