"""제안(proposal) 보관소의 단위 테스트 — 저장·목록·diff·반영·폐기 (v4 Step 3).

핵심 계약: 생성물은 apply 전까지 소스 트리에 존재하지 않고, apply 후에는
보관소에서 사라진다(이중 반영 방지).
"""

from adapters.java.maven import detect_maven_project
from cli.proposals import (
    STATUS_ACCEPTED,
    apply_proposal,
    discard_proposal,
    get_proposal,
    list_proposals,
    render_diff,
    save_proposal,
)

CODE = "class CalcDivideTest {\n    // 생성된 테스트\n}\n"
TEST_REL = "src/test/java/com/example/CalcDivideTest.java"


def _project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return detect_maven_project(tmp_path)


def _save(project, name="CalcDivideTest"):
    return save_proposal(
        project, name, "Calc#divide", TEST_REL, CODE, STATUS_ACCEPTED, ["[assert] 통과"]
    )


class TestProposalLifecycle:
    def test_저장하면_목록과_본문을_읽을_수_있다(self, tmp_path):
        project = _project(tmp_path)
        _save(project)
        proposals = list_proposals(project)
        assert [p.name for p in proposals] == ["CalcDivideTest"]
        meta, code = get_proposal(project, "CalcDivideTest")
        assert meta.target == "Calc#divide"
        assert code == CODE

    def test_apply_전에는_소스_트리에_없다(self, tmp_path):
        project = _project(tmp_path)
        _save(project)
        assert not (project.root / TEST_REL).exists()

    def test_apply하면_트리에_생기고_보관소에서_사라진다(self, tmp_path):
        project = _project(tmp_path)
        _save(project)
        dest = apply_proposal(project, "CalcDivideTest")
        assert dest.read_text(encoding="utf-8") == CODE
        assert list_proposals(project) == []  # 이중 반영 방지

    def test_diff는_새_파일이면_전체_추가로_보인다(self, tmp_path):
        project = _project(tmp_path)
        _save(project)
        diff = render_diff(project, "CalcDivideTest")
        assert "+class CalcDivideTest {" in diff
        assert "(없음)" in diff

    def test_discard하면_흔적이_없다(self, tmp_path):
        project = _project(tmp_path)
        _save(project)
        discard_proposal(project, "CalcDivideTest")
        assert list_proposals(project) == []
        assert not (project.root / TEST_REL).exists()

    def test_없는_제안은_안내와_함께_실패한다(self, tmp_path):
        project = _project(tmp_path)
        try:
            get_proposal(project, "없음")
            raise AssertionError("예외가 나야 한다")
        except FileNotFoundError as e:
            assert "cta diff" in str(e)
