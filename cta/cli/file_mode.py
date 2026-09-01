"""cta generate <파일명> — 파일 하나로 시작하는 간편 모드 (사용성 개선).

현재 폴더 기준 하위 탐색으로 파일을 찾고, 소속 Maven 프로젝트를 자동 인식한 뒤,
파일의 메서드들을 계획한다: private 제외, 기존 테스트가 이미 참조하는 메서드는
건너뜀(유지보수 — 없는 것만 채운다). --all이면 전부 생성 대상.
층: cli — 탐색·계획만 하고 생성 자체는 generate.run_generation을 쓴다.
"""

import os
import re
from pathlib import Path

from cta.adapters.java.maven import MavenProject, detect_maven_project
from cta.adapters.java.parsing import extract_methods
from cta.cli.locate import PRUNE_DIRS

# 테스트 소스에서 "식별자(" 모양을 긁어 참조 여부를 판단한다 — 근사치지만 결정적.
_CALL_LIKE = re.compile(r"\b(\w+)\s*\(")


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


def methods_referenced_in_tests(project: MavenProject) -> set[str]:
    """기존 테스트 소스가 호출 형태로 참조하는 식별자 집합.

    근사 판정인 이유: "그 메서드의 테스트가 있는가"의 정답은 커버리지 실측(그래프
    COVERS)이지만, 간편 모드는 그래프 없이도 돌아야 한다. 호출 모양 참조만으로도
    '전혀 다뤄지지 않은 메서드'를 고르는 데는 충분하다.
    """
    referenced: set[str] = set()
    if not project.test_source_dir.is_dir():
        return referenced
    for path in project.test_source_dir.rglob("*.java"):
        referenced.update(_CALL_LIKE.findall(path.read_text(encoding="utf-8", errors="replace")))
    return referenced


def plan_targets(
    project: MavenProject, class_file: Path, include_all: bool = False
) -> list[tuple[str, str | None]]:
    """파일의 메서드별 (이름, 건너뛰는 이유|None) 계획을 만든다.

    건너뜀: private 메서드 / 기존 테스트가 이미 참조하는 메서드(--all이면 무시).
    """
    source = class_file.read_text(encoding="utf-8", errors="replace")
    referenced = set() if include_all else methods_referenced_in_tests(project)
    plan: list[tuple[str, str | None]] = []
    for m in extract_methods(source):
        if m.is_test:
            continue
        signature = m.text.split("{", 1)[0]
        if "private" in signature.split():
            plan.append((m.name, "private 메서드 — 공개 동작을 통해 시험된다"))
        elif m.name in referenced:
            plan.append((m.name, "기존 테스트가 이미 참조 (강제 생성: --all)"))
        else:
            plan.append((m.name, None))
    return plan


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


def run_file_mode(args) -> int:
    """파일 이름 하나로 탐색→계획→메서드별 생성까지 수행한다."""
    from cta.cli.generate import ask_on_terminal, run_generation

    root = Path.cwd()
    class_file = resolve_file(root, args.file, args.non_interactive)
    if class_file is None:
        return 1
    project_root = project_root_for(class_file, root)
    project = detect_maven_project(project_root)
    if class_file.resolve().is_relative_to(project.test_source_dir.resolve()):
        print(f"{class_file.name}은 테스트 파일이다 — 대상은 main 소스여야 한다")
        return 1

    class_name = class_file.stem
    plan = plan_targets(project, class_file, include_all=args.all)
    todo = [name for name, skip in plan if skip is None]
    print(f"파일: {class_file.relative_to(root)}  (프로젝트: {project_root.name})")
    for name, skip in plan:
        mark = "생성 예정" if skip is None else f"건너뜀 — {skip}"
        print(f"  {class_name}#{name}: {mark}")
    if not todo:
        print("생성할 메서드가 없다 (전부 강제하려면 --all)")
        return 0

    results = []
    for method in todo:
        print(f"\n──── {class_name}#{method} ────")
        outcome = run_generation(
            project_path=str(project_root),
            target=f"{class_name}#{method}",
            instruction_extra=args.instruction,
            model_override=args.model,
            fast=args.fast,
            ask_user=None if args.non_interactive else ask_on_terminal,
        )
        results.append((method, outcome))
        if outcome["status"] == "error":
            print(f"오류: {outcome['report']}")
        else:
            summary = " / ".join(f"{n}:{'OK' if p else 'X'}" for n, p, _ in outcome["gate_results"])
            print(f"→ {outcome['status']} ({outcome['elapsed']:.0f}초)  게이트 {summary}")

    proposals = [o["proposal"] for _, o in results if o.get("proposal")]
    print(f"\n===== 요약: {len(todo)}개 중 제안 {len(proposals)}건 =====")
    if proposals:
        print("검토: cta diff")
        print("반영: cta apply  (여러 건이면 이름 지정 또는 --all)")
    failed = [m for m, o in results if o["status"] in ("not_passed", "error")]
    if failed:
        print(f"미완: {', '.join(failed)} — 위 로그의 사유 참조")
    return 0 if not failed else 2
