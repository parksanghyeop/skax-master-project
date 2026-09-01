"""의도 분류 LLM 구현 — 파이프라인에서 LLM이 등장하는 두 자리 중 하나 (v4 2.1).

대분류와 구체 분석을 **한 호출**로 받는다(비용·일관성). 출력은 JSON으로 요구하고,
파싱 실패·모르는 값은 unclear로 강등한다 — 분류기가 흔들려도 조치 결정(규칙표)이
안전한 쪽(사람에게 묻기)으로 가게 하는 방어선이다. 층: llm (R7).
"""

import json
import re
from pathlib import Path
from string import Template

from cta.core.pipeline.models import KNOWN_INTENTS, Intent
from cta.llm.client import ChatMessage, LlmClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classify_intent.md"

# 모델이 규칙을 어기고 코드 블록·설명을 붙여도 JSON 객체만 건진다
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_intent(response_text: str) -> Intent:
    """LLM 응답에서 Intent를 뽑는다. 어떤 실패도 unclear로 수렴한다(예외 없음)."""
    m = _JSON_OBJECT.search(response_text)
    if not m:
        return Intent(category="unclear", analysis=f"분류 응답 해석 불가: {response_text[:200]}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Intent(category="unclear", analysis=f"분류 JSON 파싱 실패: {response_text[:200]}")
    category = str(data.get("category", "")).strip()
    analysis = str(data.get("analysis", "")).strip() or "(분석 없음)"
    if category not in KNOWN_INTENTS:
        return Intent(category="unclear", analysis=f"모르는 분류 {category!r}: {analysis}")
    return Intent(category=category, analysis=analysis)


class PromptedIntentClassifier:
    """프롬프트 파일 + LlmClient로 의도를 분류한다 (IntentClassifier 구현)."""

    def __init__(self, client: LlmClient, model: str) -> None:
        self._client = client
        self._model = model
        self._template = Template(_PROMPT_PATH.read_text(encoding="utf-8"))

    def classify(self, change_summary: str) -> Intent:
        content = self._template.substitute(change_summary=change_summary)
        response = self._client.chat([ChatMessage(role="user", content=content)], self._model)
        return parse_intent(response.content)
