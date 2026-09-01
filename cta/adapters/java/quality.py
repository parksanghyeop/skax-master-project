"""assert 검사 최소본 — QualityChecker의 PoC 구현.

v4 2.4의 assert 검사를 "assert 호출 수 비교" 수준으로 줄인 것. 기존 테스트의
assert가 줄면 탈락, 새 테스트에 assert가 없으면 탈락. 왜 LLM을 안 쓰나:
품질 게이트는 결정적이어야 하고(R2), 수 비교는 판단이 필요 없다. AST 수준의
정밀 비교(삭제·완화·변경 구분)는 2단계 과제다. 층: adapters/java.
"""

import re
from pathlib import Path

from cta.adapters.java.maven import MavenProject

# JUnit 계열 assert 호출(assertEquals, assertThrows, assertTrue...)과 assert 문 모두 잡는다.
_ASSERT_CALL = re.compile(r"\bassert\w*\s*\(")


def count_asserts(source: str) -> int:
    return len(_ASSERT_CALL.findall(source))


class AssertCountChecker:
    """생성 시점의 assert 수를 기준선으로 저장해 두고, 검사 시점과 비교한다.

    입력: project — 기준선을 잡을 대상 프로젝트.
    check(path) 출력: "통과"/"탈락"으로 시작하는 결과 문자열.
    """

    def __init__(self, project: MavenProject) -> None:
        self._project = project
        self._baseline: dict[str, int] = {}
        test_dir = project.test_source_dir
        if test_dir.is_dir():
            for p in test_dir.rglob("*.java"):
                self._baseline[str(p.resolve())] = count_asserts(p.read_text(encoding="utf-8"))

    def check(self, path: str) -> str:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            return f"탈락: 검사할 파일이 없다 — {resolved}"
        now = count_asserts(resolved.read_text(encoding="utf-8"))
        before = self._baseline.get(str(resolved))
        if before is None:
            # 새 파일: 커버리지 숫자만 채우는 "assert 없는 빈 테스트"를 여기서 거른다(v4 2.4)
            if now == 0:
                return "탈락: 새 테스트에 assert가 없다 — 실행만 하고 검증하지 않는 테스트"
            return f"통과: 새 테스트, assert {now}개"
        if now < before:
            return (
                f"탈락: 기존 테스트의 assert 감소 "
                f"(수정 전 {before}개 → 후 {now}개) — 사람 확인 필요"
            )
        return f"통과: assert {before}개 → {now}개"
