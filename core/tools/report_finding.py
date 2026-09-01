"""도구 6/6 report_finding — 한계 보고 후 정상 종료 (v4 3절 "한계 보고").

"못 하겠다"는 실패가 아니라 정상 종료다(v4 1절) — 이 출구가 있어야 막다른
길에서의 무한 재시도가 사라진다. 종료 처리 자체는 그래프가 한다.
"""

from core.textlimit import clip


def report_finding(finding: str) -> str:
    """발견한 문제를 보고 형식으로 정리해 돌려준다."""
    return clip(f"한계 보고:\n{finding}")
