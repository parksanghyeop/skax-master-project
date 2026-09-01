"""도구 1/6 inspect_target — 대상 메서드의 형태·의존·기존 테스트 요약 (v4 3절 "대상 조사")."""

from core.ports import SourceInspector
from core.textlimit import clip


def inspect_target(inspector: SourceInspector, target: str) -> str:
    """대상 식별자를 조사해 요약 문자열을 돌려준다. 없는 대상도 문자열로 안내한다."""
    return clip(inspector.inspect(target))
