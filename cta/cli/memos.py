"""판단 메모 — 사람이 resolve로 내린 결정을 기록하고, 다음 변경 대응에서 참고로 보여준다.

시나리오 SC-002 3단계 "비슷한 과거 변경 사례를 찾아 참고 자료로 같이 보여주고".
검색은 같은 클래스·메서드 이름 일치(키워드)다 — 임베딩 검색은 게이트웨이가 제공하면
그때 바꾼다(phase3 스킬). **참고일 뿐 규칙표를 우회하지 못한다**(v4 4.2). 층: cli.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from cta.adapters.java.maven import MavenProject

MEMOS_DIR = ".cta/memos"
MAX_SHOWN = 3  # 참고 사례는 많아야 3건 — 화면·프롬프트 모두


@dataclass(frozen=True)
class Memo:
    """판단 메모 한 건 — 어떤 대상에 대해 사람이 무엇을 왜 결정했나."""

    target: str  # "Class#method"
    category: str  # 그때의 의도 분류
    decision: str  # 사람의 결정 (intended / test-issue / proceed / skip)
    note: str  # 한 줄 설명
    created_at: str


def _dir(project: MavenProject) -> Path:
    return project.root / MEMOS_DIR


def save_memo(project: MavenProject, memo: Memo) -> Path:
    d = _dir(project)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = d / f"{stamp}.json"
    path.write_text(json.dumps(asdict(memo), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_memos(project: MavenProject) -> list[Memo]:
    d = _dir(project)
    if not d.is_dir():
        return []
    return [Memo(**json.loads(p.read_text(encoding="utf-8"))) for p in sorted(d.glob("*.json"))]


def find_similar(project: MavenProject, target: str) -> list[Memo]:
    """같은 메서드 → 같은 클래스 순으로 최근 것부터 최대 MAX_SHOWN건."""
    class_name = target.split("#", 1)[0]
    memos = list_memos(project)
    same_method = [m for m in memos if m.target == target]
    same_class = [m for m in memos if m.target != target and m.target.startswith(class_name + "#")]
    return (list(reversed(same_method)) + list(reversed(same_class)))[:MAX_SHOWN]


def render_memos(memos: list[Memo]) -> str:
    """ "참고" 줄에 들어갈 문자열. 없으면 빈 값(호출부가 '없음'을 찍는다)."""
    if not memos:
        return ""
    parts = [
        f"{m.created_at[:10]} {m.target.replace('#', '.')}: {m.category} → {m.decision} ({m.note})"
        for m in memos
    ]
    return " / ".join(parts)
