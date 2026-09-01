"""프로젝트 자동 인식(cli/locate)과 제안 자동 선택(select_names)의 단위 테스트.

인자 생략 시 기본값 규칙 검증: 프로젝트 안→그 프로젝트, 작업 폴더→하위 탐색
(하나면 자동·여럿이면 지정 요구), 제안 1건이면 이름 생략 가능.
"""

from pathlib import Path

from cli.locate import find_maven_projects, resolve_project
from cli.proposals import save_proposal, select_names


def make_project(root: Path, name: str) -> Path:
    proj = root / name
    proj.mkdir(parents=True)
    (proj / "pom.xml").write_text("<project/>", encoding="utf-8")
    return proj


def test_explicit_project_wins(tmp_path, monkeypatch):
    proj = make_project(tmp_path, "svc")
    monkeypatch.chdir(tmp_path)
    assert resolve_project(str(proj)).root == proj.resolve()


def test_inside_project_resolves_to_it(tmp_path, monkeypatch):
    proj = make_project(tmp_path, "svc")
    sub = proj / "src" / "main"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)  # 프로젝트 하위 폴더에서 실행해도 위로 올라가 찾는다
    assert resolve_project(None).root == proj.resolve()


def test_workdir_with_single_project_auto_detects(tmp_path, monkeypatch, capsys):
    proj = make_project(tmp_path, "svc")
    monkeypatch.chdir(tmp_path)
    assert resolve_project(None).root == proj.resolve()
    assert "자동 인식" in capsys.readouterr().out


def test_workdir_with_many_projects_requires_choice(tmp_path, monkeypatch):
    make_project(tmp_path, "svc-a")
    make_project(tmp_path, "svc-b")
    monkeypatch.chdir(tmp_path)
    assert resolve_project(None, non_interactive=True) is None


def test_no_project_anywhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_project(None) is None


def test_find_projects_does_not_descend_into_project(tmp_path):
    proj = make_project(tmp_path, "svc")
    make_project(proj, "nested")  # 프로젝트 안의 pom은 세지 않는다(단일 모듈 전제)
    assert find_maven_projects(tmp_path) == [proj]


def test_select_names_defaults_to_single_pending(tmp_path):
    from adapters.java.maven import detect_maven_project

    proj = make_project(tmp_path, "svc")
    project = detect_maven_project(proj)
    save_proposal(project, "FooTest", "Foo#bar", "src/test/java/FooTest.java", "x", "accepted", [])
    assert select_names(project, None, all_flag=False) == ["FooTest"]

    save_proposal(project, "BazTest", "Baz#qux", "src/test/java/BazTest.java", "x", "accepted", [])
    assert select_names(project, None, all_flag=False) is None  # 여럿이면 추측 금지
    assert select_names(project, "BazTest", all_flag=False) == ["BazTest"]
    assert sorted(select_names(project, None, all_flag=True)) == ["BazTest", "FooTest"]
