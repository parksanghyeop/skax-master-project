"""사람 확인 보관소 — escalate/ask 결정을 저장하고 멈춘 뒤, resolve로 이어서 실행한다.

시나리오 SC-003 6~8단계: "현재 상태를 저장한 뒤 멈춘다 → 판단 전달 기능으로 알려주면
저장해 둔 상태를 불러와 멈춘 지점부터 이어서 실행한다". 저장 위치는 제안(proposals)과
같은 `<프로젝트>/.cta/` 아래다. 층: cli (ADR-0015 D3).
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from cta.adapters.java.maven import MavenProject

ESCALATIONS_DIR = ".cta/escalations"  # 프로젝트 밑 — gitignore(.cta/) 대상


@dataclass(frozen=True)
class Escalation:
    """멈춘 지점의 상태 — resolve가 이어서 실행하는 데 필요한 전부."""

    id: str
    kind: str  # "escalate"(리팩터링인데 실패) | "ask"(분류 불확실·커버 테스트 없음)
    target: str  # "Class#method"
    category: str  # 의도 대분류
    confidence: float
    evidence: list[str]
    analysis: str
    reason: str  # 규칙표 사유
    briefing: str  # 작업 지침서
    tests: list[str]  # 검증 테스트 selector들
    run_summary: str  # 기존 테스트 실행 요약
    failed_tests: list[dict]  # [{name, test_class, expected, actual, message}]
    file_rel: str
    change_line: int
    diff_excerpt: str
    base: str  # 비교 기준(HEAD~1 등)
    commit_message: str
    created_at: str
    status: str = "open"
    extra: dict = field(default_factory=dict)


def _dir(project: MavenProject) -> Path:
    return project.root / ESCALATIONS_DIR


def make_id(target: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^\w]+", "-", target).strip("-")
    return f"{stamp}-{safe}"


def save_escalation(project: MavenProject, escalation: Escalation) -> Path:
    d = _dir(project)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{escalation.id}.json"
    path.write_text(json.dumps(asdict(escalation), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_escalations(project: MavenProject) -> list[Escalation]:
    d = _dir(project)
    if not d.is_dir():
        return []
    return [
        Escalation(**json.loads(p.read_text(encoding="utf-8"))) for p in sorted(d.glob("*.json"))
    ]


def get_escalation(project: MavenProject, escalation_id: str) -> Escalation:
    path = _dir(project) / f"{escalation_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"사람 확인 항목 {escalation_id!r}이 없다 — `cta resolve`로 목록 확인"
        )
    return Escalation(**json.loads(path.read_text(encoding="utf-8")))


def discard_escalation(project: MavenProject, escalation_id: str) -> None:
    (_dir(project) / f"{escalation_id}.json").unlink(missing_ok=True)
