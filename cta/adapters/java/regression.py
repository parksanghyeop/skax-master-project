"""게이트 ⑥ regression — 재발 방지 테스트가 **수정 전 코드에서 실패하는지** 확인 (SC-002 7단계).

버그를 고친 커밋에 붙이는 테스트는 그 버그가 있던 코드에서 실패해야 의미가 있다.
수정 전 코드에서도 통과하면 "버그를 잡지 못하는 테스트"이므로 탈락시키고, 사유를
지침서에 붙여 다시 만들게 한다. 검사 방법: 변경된 main 소스를 수정 전 내용으로
잠시 바꿔 끼우고 생성 테스트만 실행한 뒤 반드시 원상 복구한다(try/finally).
LLM 판단 없음(R2). 층: adapters/java (ADR-0015 D4).
"""

from cta.adapters.java.maven import MavenProject
from cta.core.gates import GateResult
from cta.core.ports import TestRunner


class BugReproductionGate:
    """수정 전 소스로 되돌린 상태에서 selector를 실행해, 실패해야 통과로 판정한다.

    입력: old_sources — {프로젝트 기준 상대 경로: 수정 전 내용 또는 None(신규 파일)}.
      내용이 하나도 없으면 측정 불가 → 탈락(보수적, v4 2.4).
    """

    name = "regression"

    def __init__(
        self,
        project: MavenProject,
        runner: TestRunner,
        old_sources: dict[str, str | None],
        selector: str,
    ) -> None:
        self._project = project
        self._runner = runner
        self._old_sources = old_sources
        self._selector = selector

    def check(self) -> GateResult:
        swappable = {rel: old for rel, old in self._old_sources.items() if old is not None}
        if not swappable:
            return GateResult(
                self.name,
                False,
                "수정 전 코드를 찾지 못해 재발 방지 여부를 확인할 수 없다(측정 불가)",
            )
        current: dict[str, str] = {}
        try:
            # 흐름: 현재 내용 보관 → 수정 전 내용으로 교체 → 테스트 실행 → finally에서 복구
            for rel, old in swappable.items():
                path = self._project.root / rel
                current[rel] = path.read_text(encoding="utf-8")
                path.write_text(old, encoding="utf-8")
            result = self._runner.run(self._selector)
        finally:
            for rel, text in current.items():
                (self._project.root / rel).write_text(text, encoding="utf-8")
        if result.passed:
            return GateResult(
                self.name,
                False,
                "수정 전 코드에서도 테스트가 통과했다 — 이 버그를 잡는 테스트가 아니다. "
                "수정 전후 동작이 갈리는 입력(경계값)을 시험하라",
            )
        return GateResult(self.name, True, "수정 전 코드에서 실패함 (정상 — 버그를 잡는 테스트)")
