"""cta generate <파일명> 간편 모드의 탐색·계획 로직 테스트.

실 LLM·Docker 없이 파일 트리만으로 검증한다: 파일 찾기(프루닝·중복),
프로젝트 루트 판별. 메서드 선정은 tests/test_materials.py가 검증한다.
"""

from pathlib import Path

from cta.cli.file_mode import find_source_files, project_root_for, resolve_file

CALCULATOR = """
public class Calculator {
    public int add(int a, int b) { return a + b; }
    public int divide(int a, int b) { return a / b; }
    private int helper(int a) { return a; }
}
"""


def make_project(root: Path, name: str = "svc") -> Path:
    proj = root / name
    main = proj / "src" / "main" / "java" / "com" / "ex"
    main.mkdir(parents=True)
    (proj / "pom.xml").write_text("<project/>", encoding="utf-8")
    (main / "Calculator.java").write_text(CALCULATOR, encoding="utf-8")
    return proj


def test_find_source_files_searches_subfolders_and_accepts_bare_name(tmp_path):
    make_project(tmp_path)
    assert len(find_source_files(tmp_path, "Calculator.java")) == 1
    assert len(find_source_files(tmp_path, "Calculator")) == 1  # .java 생략 허용


def test_find_source_files_prunes_build_dirs(tmp_path):
    proj = make_project(tmp_path)
    ghost = proj / "target" / "classes"
    ghost.mkdir(parents=True)
    (ghost / "Calculator.java").write_text("x", encoding="utf-8")
    assert len(find_source_files(tmp_path, "Calculator")) == 1


def test_project_root_for_walks_up_to_pom(tmp_path):
    proj = make_project(tmp_path)
    file = proj / "src" / "main" / "java" / "com" / "ex" / "Calculator.java"
    assert project_root_for(file, tmp_path) == proj.resolve()


def test_project_root_for_none_when_no_pom(tmp_path):
    orphan = tmp_path / "loose" / "Calculator.java"
    orphan.parent.mkdir()
    orphan.write_text(CALCULATOR, encoding="utf-8")
    assert project_root_for(orphan, tmp_path) is None


def test_resolve_file_ambiguous_in_non_interactive_returns_none(tmp_path, capsys):
    make_project(tmp_path, "svc-a")
    make_project(tmp_path, "svc-b")
    assert resolve_file(tmp_path, "Calculator", non_interactive=True) is None
    out = capsys.readouterr().out
    assert "2개" in out


def test_resolve_file_single_match(tmp_path):
    proj = make_project(tmp_path)
    got = resolve_file(tmp_path, "Calculator", non_interactive=True)
    assert got == proj / "src" / "main" / "java" / "com" / "ex" / "Calculator.java"
