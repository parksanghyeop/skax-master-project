"""의도 분류 LLM 구현 — 파이프라인에서 LLM이 등장하는 두 자리 중 하나 (v4 2.1).

변경 **한 건마다** 대분류·확신도·근거·구체 분석을 한 호출로 받는다(ADR-0015 D2).
출력은 JSON으로 요구하고, 파싱 실패·모르는 값은 unclear로 강등한다 — 분류기가
흔들려도 조치 결정(규칙표)이 안전한 쪽(사람에게 묻기)으로 가게 하는 방어선이다.
층: llm (R7).
"""

import json
import re
from pathlib import Path
from string import Template

from cta.core.pipeline.models import KNOWN_INTENTS, ChangedSymbol, ChangeSet, Intent
from cta.llm.client import ChatMessage, LlmClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classify_intent.md"

# 모델이 규칙을 어기고 코드 블록·설명을 붙여도 JSON 객체만 건진다
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

# 근거 목록 상한 — 화면에 보여주는 용도라 길면 오히려 안 읽힌다
MAX_EVIDENCE = 4


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
    confidence = _parse_confidence(data.get("confidence"))
    evidence = _parse_evidence(data.get("evidence"))
    if category not in KNOWN_INTENTS:
        return Intent(
            category="unclear",
            analysis=f"모르는 분류 {category!r}: {analysis}",
            confidence=0.0,
            evidence=evidence,
        )
    return Intent(category=category, analysis=analysis, confidence=confidence, evidence=evidence)


def _parse_confidence(raw) -> float:
    """0~100 정수(또는 0~1 실수)를 0.0~1.0으로 정규화한다. 이상한 값은 0.0."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value > 1.0:  # 0~100 척도로 답한 경우
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _parse_evidence(raw) -> tuple[str, ...]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())[:MAX_EVIDENCE]


def describe_clues(change: ChangedSymbol, change_set: ChangeSet) -> list[str]:
    """일반 코드가 모은 단서를 사람이 읽을 한 줄들로 만든다 — 프롬프트와 화면이 공유."""
    clues = []
    if change_set.commit_message.strip():
        first = change_set.commit_message.strip().splitlines()[0]
        clues.append(f"커밋 메시지: {first}")
    else:
        clues.append("커밋 메시지: 없음 (미커밋 변경)")
    if change_set.issue_refs:
        clues.append(f"이슈 참조: {', '.join(change_set.issue_refs)}")
    clues.append(
        "메서드 시그니처: 변경됨" if change.signature_changed else "메서드 시그니처: 그대로"
    )
    clues.append("접근 제어자: 변경됨" if change.access_changed else "접근 제어자: 그대로")
    clues.append(f"바뀐 줄 수: +{change.lines_added} / -{change.lines_removed}")
    return clues


class PromptedIntentClassifier:
    """프롬프트 파일 + LlmClient로 변경 한 건의 의도를 분류한다 (IntentClassifier 구현)."""

    def __init__(self, client: LlmClient, model: str) -> None:
        self._client = client
        self._model = model
        self._template = Template(_PROMPT_PATH.read_text(encoding="utf-8"))

    def classify(self, change: ChangedSymbol, change_set: ChangeSet, memos: str = "") -> Intent:
        """변경 한 건을 분류한다. memos: 비슷한 과거 판단 사례 문자열(참고용, 없으면 빈 값)."""
        content = self._template.substitute(
            target=change.target,
            clues="\n".join(f"- {c}" for c in describe_clues(change, change_set)),
            diff=change.diff_excerpt or "(발췌 없음)",
            memos=memos or "없음",
        )
        response = self._client.chat([ChatMessage(role="user", content=content)], self._model)
        return parse_intent(response.content)
