"""품질 게이트 실행기와 설정 — 마지막 검문소의 틀 (M6, v4 2.4).

왜 LLM이 없는가(R2): 여기서 묻는 것은 "좋은 테스트인가"(판단)가 아니라
"측정 가능한 규칙을 어겼는가"(사실)다. 잘못 탈락시키는 일은 있어도 잘못
통과시키는 일은 없게, 모든 게이트는 보수적으로 기운다 — 애매하면 탈락시키고
사람 확인 목록으로 보낸다(v4 2.4). 테스트를 만든 에이전트는 판정에 관여하지 못한다.
층: core — 게이트 실행·집계는 언어 무관, 개별 게이트 구현은 adapters에 있다.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# 기준치 기본값 (v4 2.4 — 설정 파일로 조정 가능).
# 100%가 아닌 이유: 방어 코드처럼 정상 경로로 도달 불가능한 라인이 있다.
DEFAULT_LINE_MIN = 0.80  # 변경 라인 커버리지 하한
DEFAULT_BRANCH_MIN = 0.70  # 분기 커버리지 하한
DEFAULT_MAX_RETRIES = 3  # 탈락 → 사유 반환 → 재시도 상한. 초과 시 사람 확인 목록
DEFAULT_MUTATION_MIN = 0.5  # 심은 버그 검출률 하한 — 임시값, M7 하네스로 보정 예정

CONFIG_FILE_NAME = "cta.toml"  # 대상 프로젝트 루트에 두면 기준치를 덮어쓴다


@dataclass(frozen=True)
class GateConfig:
    """게이트 기준치 설정. 읽기는 load_gate_config로만 한다."""

    line_min: float = DEFAULT_LINE_MIN
    branch_min: float = DEFAULT_BRANCH_MIN
    max_retries: int = DEFAULT_MAX_RETRIES
    mutation_min: float = DEFAULT_MUTATION_MIN


def load_gate_config(project_root: str | Path) -> GateConfig:
    """프로젝트 루트의 cta.toml에서 [gates] 절을 읽는다. 없으면 기본값.

    형식 예:
        [gates]
        line_min = 0.9
        branch_min = 0.8
        max_retries = 2
    """
    path = Path(project_root) / CONFIG_FILE_NAME
    if not path.is_file():
        return GateConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8")).get("gates", {})
    return GateConfig(
        line_min=float(data.get("line_min", DEFAULT_LINE_MIN)),
        branch_min=float(data.get("branch_min", DEFAULT_BRANCH_MIN)),
        max_retries=int(data.get("max_retries", DEFAULT_MAX_RETRIES)),
        mutation_min=float(data.get("mutation_min", DEFAULT_MUTATION_MIN)),
    )


@dataclass(frozen=True)
class GateResult:
    """게이트 하나의 판정. reason은 탈락 사유(또는 통과 요약) — 재시도 프롬프트에 쓰인다."""

    name: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class GateReport:
    """게이트 전체 실행 결과. 하나라도 탈락이면 불합격."""

    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failure_reasons(self) -> str:
        """탈락 사유 모음 — 재시도 시 모델에게 그대로 반환한다(v4 2.4 '탈락했을 때')."""
        return "\n".join(f"[{r.name}] {r.reason}" for r in self.results if not r.passed)


class Gate(Protocol):
    """게이트 하나 — 결정적 검사. check는 예외 대신 GateResult로 판정을 돌려준다."""

    name: str

    def check(self) -> GateResult: ...


def run_gates(gates: list[Gate]) -> GateReport:
    """게이트를 전부 실행한다(단락 없음 — 탈락 사유를 한 번에 모아 반환해야
    재시도가 한 바퀴로 끝난다)."""
    return GateReport(results=[g.check() for g in gates])
