"""도구 5/6 check_quality — 품질 지표 조회 (v4 3절 "품질 확인").

PoC 범위: assert 검사 최소본만 연결. 커버리지·뮤테이션은 2단계에서 붙는다.
"""

from core.ports import QualityChecker
from core.textlimit import clip


def check_quality(checker: QualityChecker, path: str) -> str:
    """path의 테스트에 대한 기계적 품질 검사 결과를 돌려준다."""
    return clip(checker.check(path))
