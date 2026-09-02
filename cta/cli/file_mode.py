"""cta generate <파일명> — 파일 이름 하나로 대상 클래스를 찾는 탐색 로직 (사용성).

현재 폴더 기준 하위 탐색으로 파일을 찾고, 소속 Maven 프로젝트를 pom.xml 상향 탐색으로
정한다. 메서드 선정·재료 수집은 adapters/java/materials가, 생성은 generate가 맡는다.
층: cli — 탐색만 한다.
"""

import os
from pathlib import Path

from cta.cli.locate import PRUNE_DIRS


def find_source_files(root: Path, name: str) -> list[Path]:
    """root 하위에서 이름이 일치하는 .java 파일을 전부 찾는다 (프루닝 포함)."""
    filename = name if name.endswith(".java") else f"{name}.java"
    matches: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        if filename in filenames:
            matches.append(Path(dirpath) / filename)
    return sorted(matches)


def project_root_for(file: Path, stop: Path) -> Path | None:
    """파일에서 위로 올라가며 pom.xml이 있는 프로젝트 루트를 찾는다 (stop까지만)."""
    for parent in file.resolve().parents:
        if (parent / "pom.xml").is_file():
            return parent
        if parent == stop.resolve():
            break
    return None


def resolve_file(root: Path, name: str, non_interactive: bool) -> Path | None:
    """이름으로 파일을 확정한다. 여러 개면 번호로 고르게 하고, 무인 모드면 안내 후 None."""
    found = find_source_files(root, name)
    matches = [m for m in found if project_root_for(m, root) is not None]
    if not matches:
        if found:
            print(f"'{name}'을 찾았지만 소속 Maven 프로젝트(pom.xml)가 없다:")
            for m in found:
                print(f"  - {m.relative_to(root)}")
        else:
            print(f"'{name}' 파일을 {root} 하위에서 찾지 못했다")
        return None
    if len(matches) == 1:
        return matches[0]
    print(f"'{name}' 이름의 파일이 {len(matches)}개다:")
    for i, m in enumerate(matches, 1):
        print(f"  {i}) {m.relative_to(root)}")
    if non_interactive:
        print("--non-interactive에서는 자동 선택하지 않는다 — 경로를 좁혀 다시 실행하라")
        return None
    try:
        # EOFError: 파이프·CI처럼 stdin이 없는 환경 — 죽지 말고 경로 지정을 요구한다
        raw = input("번호 선택: ").lstrip("﻿").strip()
        return matches[int(raw) - 1]
    except (ValueError, IndexError, EOFError):
        print("잘못된 선택 — 경로를 좁혀 다시 실행하라")
        return None
