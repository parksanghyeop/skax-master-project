"""테스트 제안(proposal) 보관소 — 생성 결과의 검토·반영·폐기 (v4 Step 3).

에이전트 출력이 곧바로 소스 트리에 남으면 "자동으로 코드가 바뀌는" 도구가 된다.
그래서 생성물은 `<프로젝트>/.cta/proposals/`에 보관하고, 반영은 사용자의
apply 명령으로만 일어난다. 층: cli.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cta.adapters.java.maven import MavenProject

PROPOSALS_DIR = ".cta/proposals"  # 프로젝트 밑 — gitignore(.cta/) 대상

STATUS_ACCEPTED = "accepted"  # 게이트 전부 통과 — 반영 권장
STATUS_NEEDS_REVIEW = "needs_review"  # 게이트 탈락(재시도 소진) — 사람 확인 필요


@dataclass(frozen=True)
class Proposal:
    """제안 하나의 메타데이터. 코드 본문은 같은 이름의 .java 파일에 있다."""

    name: str  # 테스트 클래스 이름 (파일·식별자 겸용)
    target: str  # 대상 "클래스#메서드"
    test_rel: str  # 반영될 경로 (프로젝트 기준 상대)
    status: str  # STATUS_*
    gate_summary: list[str]  # 게이트별 한 줄 판정
    created_at: str


def _dir(project: MavenProject) -> Path:
    return project.root / PROPOSALS_DIR


def save_proposal(
    project: MavenProject,
    name: str,
    target: str,
    test_rel: str,
    code: str,
    status: str,
    gate_summary: list[str],
) -> Proposal:
    """제안을 저장한다. 같은 이름이 있으면 덮어쓴다(최신 생성이 우선)."""
    d = _dir(project)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.java").write_text(code, encoding="utf-8")
    proposal = Proposal(
        name=name,
        target=target,
        test_rel=test_rel,
        status=status,
        gate_summary=gate_summary,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    (d / f"{name}.json").write_text(
        json.dumps(proposal.__dict__, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return proposal


def list_proposals(project: MavenProject) -> list[Proposal]:
    d = _dir(project)
    if not d.is_dir():
        return []
    result = []
    for meta in sorted(d.glob("*.json")):
        data = json.loads(meta.read_text(encoding="utf-8"))
        result.append(Proposal(**data))
    return result


def select_names(project: MavenProject, name: str | None, all_flag: bool) -> list[str] | None:
    """apply/discard가 다룰 제안 이름들을 정한다. 정하지 못하면 None(사유 출력됨).

    기본값 규칙: 이름 생략 시 대기 제안이 정확히 1건이면 그것 — 인자 없이도
    흔한 경우(방금 생성한 1건)가 동작하게 한다. 여럿이면 추측하지 않는다.
    """
    pending = [p.name for p in list_proposals(project)]
    if not pending:
        print("대기 중인 제안 없음")
        return None
    if all_flag:
        return pending
    if name:
        return [name]
    if len(pending) == 1:
        print(f"제안이 1건이라 자동 선택: {pending[0]}")
        return pending
    print(f"제안이 {len(pending)}건이다 — 이름 또는 --all을 지정하라: {', '.join(pending)}")
    return None


def get_proposal(project: MavenProject, name: str) -> tuple[Proposal, str]:
    """(메타, 코드 본문)을 돌려준다. 없으면 FileNotFoundError."""
    d = _dir(project)
    meta = d / f"{name}.json"
    if not meta.is_file():
        raise FileNotFoundError(f"제안 {name!r}이 없다 — `cta diff`로 목록 확인")
    data = json.loads(meta.read_text(encoding="utf-8"))
    code = (d / f"{name}.java").read_text(encoding="utf-8")
    return Proposal(**data), code


def render_diff(project: MavenProject, name: str) -> str:
    """제안과 현재 트리의 차이를 통합 diff 형식 문자열로 만든다."""
    import difflib

    proposal, code = get_proposal(project, name)
    dest = project.root / proposal.test_rel
    old_lines = dest.read_text(encoding="utf-8").splitlines(keepends=True) if dest.is_file() else []
    diff = difflib.unified_diff(
        old_lines,
        code.splitlines(keepends=True),
        fromfile=f"현재: {proposal.test_rel}" + ("" if old_lines else " (없음)"),
        tofile=f"제안: {name}",
    )
    return "".join(diff) or "(차이 없음 — 이미 반영된 내용과 동일)"


def apply_proposal(project: MavenProject, name: str) -> Path:
    """제안을 테스트 트리에 반영하고 제안 보관소에서 지운다."""
    proposal, code = get_proposal(project, name)
    dest = project.root / proposal.test_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(code, encoding="utf-8")
    discard_proposal(project, name)
    return dest


def discard_proposal(project: MavenProject, name: str) -> None:
    d = _dir(project)
    (d / f"{name}.java").unlink(missing_ok=True)
    (d / f"{name}.json").unlink(missing_ok=True)
