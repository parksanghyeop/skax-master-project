"""Maven 프로젝트 자동 인식 — --project 생략을 가능하게 하는 공통 로직.

Diffblue Cover CLI의 관례를 따른다: 인자 없이 실행하면 현재 위치에서 프로젝트를
찾고, 지정은 좁힐 때만 한다. 탐색 순서: 현재 폴더·상위(안에서 실행) → 하위
폴더(작업 폴더에서 실행, 하나면 자동·여럿이면 번호 선택).
층: cli — 모든 서브커맨드가 이 모듈로 프로젝트를 정한다.
"""

import os
from pathlib import Path

from cta.adapters.java.maven import MavenProject, detect_maven_project

# 탐색에서 건너뛸 폴더 — 빌드 산출물·캐시·다른 도구의 둥지
PRUNE_DIRS = {".git", ".cta", "target", "build", "out", ".venv", "node_modules", ".idea"}


def find_maven_projects(root: Path) -> list[Path]:
    """root 하위에서 pom.xml이 있는 프로젝트 루트들을 찾는다.

    프로젝트를 찾으면 그 안으로는 내려가지 않는다 — 단일 모듈 전제(v4)라
    최상위 pom이 곧 프로젝트다.
    """
    projects: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        if "pom.xml" in filenames:
            projects.append(Path(dirpath))
            dirnames[:] = []  # 프로젝트 내부는 더 탐색하지 않음
    return sorted(projects)


def resolve_project(explicit: str | None, non_interactive: bool = False) -> MavenProject | None:
    """--project 값이 없으면 현재 위치에서 프로젝트를 자동으로 정한다.

    입력: explicit — 사용자가 준 --project 값(없으면 None).
    반환: MavenProject, 정하지 못하면 None(사유는 이미 출력됨).
    """
    if explicit:
        return detect_maven_project(explicit)

    # 1) 프로젝트 안(또는 하위 폴더)에서 실행한 경우 — 위로 올라가며 pom을 찾는다
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pom.xml").is_file():
            return MavenProject(root=candidate)

    # 2) 작업 폴더(프로젝트들의 부모)에서 실행한 경우 — 하위에서 찾는다
    projects = find_maven_projects(cwd)
    if not projects:
        print(f"Maven 프로젝트를 찾지 못했다 ({cwd} 기준) — --project로 지정하라")
        return None
    if len(projects) == 1:
        print(f"프로젝트 자동 인식: {projects[0].relative_to(cwd)}")
        return detect_maven_project(projects[0])
    print(f"프로젝트가 {len(projects)}개다:")
    for i, p in enumerate(projects, 1):
        print(f"  {i}) {p.relative_to(cwd)}")
    if non_interactive:
        print("--project로 지정하라 (무인 모드에서는 자동 선택하지 않는다)")
        return None
    try:
        # EOFError: 파이프·CI처럼 stdin이 없는 환경 — 죽지 말고 지정을 요구한다
        raw = input("번호 선택: ").lstrip("﻿").strip()
        return detect_maven_project(projects[int(raw) - 1])
    except (ValueError, IndexError, EOFError):
        print("잘못된 선택 — --project로 지정하라")
        return None
