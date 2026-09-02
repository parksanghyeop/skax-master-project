"""게이트 불변식 테스트 — 악의적 시나리오를 게이트가 막는지 검증 (M6 핵심 테스트).

phase2 스킬의 최소 세트: assert 완화 / @Disabled / 허용 목록 밖 수정 → 전부 탈락.
(④ 커버리지·⑤ 뮤테이션의 실측 불변식은 docker 마커의 통합 테스트에 있고,
여기서는 판정 로직을 리포트 고정값으로 검증한다.)
이 테스트들이 초록이면 게이트가 사양대로 작동한다는 증거다.
"""

from pathlib import Path

from cta.adapters.java.gates import (
    AssertIntegrityGate,
    FileScopeGate,
    SkipAnnotationGate,
    snapshot_baseline,
)
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.mutation import parse_mutations, write_overlay_pom
from cta.adapters.java.parsing import extract_assert_statements
from cta.core.gates import load_gate_config, run_gates

ORIGINAL_TEST = """\
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalcTest {
    @Test
    void add_twoPositives_returnsSum() {
        assertEquals(7, new Calc().add(3, 4));
    }
}
"""

MAIN = """\
package com.example;

public class Calc {
    public int add(int a, int b) { return a + b; }
}
"""


def _project(tmp_path: Path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    main = tmp_path / "src" / "main" / "java" / "com" / "example"
    test = tmp_path / "src" / "test" / "java" / "com" / "example"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    (main / "Calc.java").write_text(MAIN, encoding="utf-8")
    (test / "CalcTest.java").write_text(ORIGINAL_TEST, encoding="utf-8")
    return detect_maven_project(tmp_path)


TEST_FILE = "src/test/java/com/example/CalcTest.java"
NEW_TEST_FILE = "src/test/java/com/example/CalcDivideTest.java"


class TestAssertIntegrityInvariants:
    def test_불변식1_assertEquals를_assertNotNull로_바꾸면_탈락한다(self, tmp_path):
        # 모델이 실패를 피하려고 검증을 완화하는 대표 시나리오 (v4가 경계하는 사고)
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        tampered = ORIGINAL_TEST.replace(
            "assertEquals(7, new Calc().add(3, 4));", "assertNotNull(new Calc().add(3, 4));"
        )
        (project.root / TEST_FILE).write_text(tampered, encoding="utf-8")
        result = AssertIntegrityGate(project, baseline).check()
        assert result.passed is False
        assert "assertEquals(7" in result.reason  # 어느 assert가 훼손됐는지 알려준다

    def test_기존_assert를_지워도_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        tampered = ORIGINAL_TEST.replace("assertEquals(7, new Calc().add(3, 4));", "")
        (project.root / TEST_FILE).write_text(tampered, encoding="utf-8")
        assert AssertIntegrityGate(project, baseline).check().passed is False

    def test_테스트_파일을_지우면_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        (project.root / TEST_FILE).unlink()
        result = AssertIntegrityGate(project, baseline).check()
        assert result.passed is False
        assert "삭제" in result.reason

    def test_새_assert_추가는_통과다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        added = ORIGINAL_TEST.replace(
            "assertEquals(7, new Calc().add(3, 4));",
            "assertEquals(7, new Calc().add(3, 4));\n"
            "        assertEquals(0, new Calc().add(0, 0));",
        )
        (project.root / TEST_FILE).write_text(added, encoding="utf-8")
        assert AssertIntegrityGate(project, baseline).check().passed is True


class TestSkipAnnotationInvariant:
    def test_불변식2_Disabled를_붙이면_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        tampered = ORIGINAL_TEST.replace("@Test", "@org.junit.jupiter.api.Disabled\n    @Test")
        (project.root / TEST_FILE).write_text(tampered, encoding="utf-8")
        result = SkipAnnotationGate(project, baseline).check()
        assert result.passed is False
        assert "스킵" in result.reason

    def test_새_파일에_Disabled가_있어도_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        (project.root / NEW_TEST_FILE).write_text(
            "@Disabled class CalcDivideTest {}", encoding="utf-8"
        )
        assert SkipAnnotationGate(project, baseline).check().passed is False


class TestFileScopeInvariant:
    def test_불변식3_허용_목록_밖_소스를_수정하면_탈락한다(self, tmp_path):
        # 모델이 테스트를 통과시키려고 대상 코드를 고쳐버리는 시나리오
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        main = project.root / "src" / "main" / "java" / "com" / "example" / "Calc.java"
        main.write_text(MAIN.replace("a + b", "7"), encoding="utf-8")
        result = FileScopeGate(project, baseline, allowed={NEW_TEST_FILE}).check()
        assert result.passed is False
        assert "Calc.java" in result.reason

    def test_허용된_새_테스트_파일만_만들면_통과다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        (project.root / NEW_TEST_FILE).write_text("class CalcDivideTest {}", encoding="utf-8")
        assert FileScopeGate(project, baseline, allowed={NEW_TEST_FILE}).check().passed is True


class TestGateAggregation:
    def test_하나라도_탈락이면_불합격이고_사유가_모인다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        (project.root / TEST_FILE).write_text(
            ORIGINAL_TEST.replace("@Test", "@Disabled\n    @Test").replace(
                "assertEquals(7", "assertNotNull(7"
            ),
            encoding="utf-8",
        )
        report = run_gates(
            [
                AssertIntegrityGate(project, baseline),
                SkipAnnotationGate(project, baseline),
                FileScopeGate(project, baseline, allowed={TEST_FILE}),
            ]
        )
        assert report.passed is False
        assert "[assert]" in report.failure_reasons
        assert "[skip]" in report.failure_reasons
        assert "[scope]" not in report.failure_reasons  # TEST_FILE은 허용 목록에 있다


class TestGateConfig:
    def test_설정_파일이_없으면_기본값이다(self, tmp_path):
        config = load_gate_config(tmp_path)
        assert (config.line_min, config.branch_min) == (0.80, 0.70)
        assert config.max_retries == 3

    def test_cta_toml로_기준치를_조정한다(self, tmp_path):
        (tmp_path / "cta.toml").write_text(
            "[gates]\nline_min = 0.9\nmax_retries = 2\n", encoding="utf-8"
        )
        config = load_gate_config(tmp_path)
        assert config.line_min == 0.9
        assert config.branch_min == 0.70  # 안 적은 값은 기본값 유지
        assert config.max_retries == 2


MUTATIONS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mutations>
  <mutation status="KILLED">
    <mutatedMethod>divide</mutatedMethod>
    <lineNumber>4</lineNumber><description>조건 뒤집기</description>
  </mutation>
  <mutation status="SURVIVED">
    <mutatedMethod>divide</mutatedMethod>
    <lineNumber>5</lineNumber><description>상수 바꾸기</description>
  </mutation>
  <mutation status="NO_COVERAGE">
    <mutatedMethod>add</mutatedMethod>
    <lineNumber>6</lineNumber><description>반환값 바꾸기</description>
  </mutation>
</mutations>
"""


class TestMutationPieces:
    def test_뮤테이션_리포트를_집계한다(self):
        killed, total, survived = parse_mutations(MUTATIONS_XML)
        assert (killed, total) == (1, 3)
        assert any("상수 바꾸기" in s for s in survived)

    def test_대상_메서드의_변형만_집계할_수_있다(self):
        # 다른 메서드(add)의 미커버 변형이 divide 판정을 오염시키면 안 된다
        killed, total, survived = parse_mutations(MUTATIONS_XML, methods={"divide"})
        assert (killed, total) == (1, 2)
        assert all("반환값" not in s for s in survived)

    def test_overlay_pom은_원본을_건드리지_않고_PIT를_끼운다(self, tmp_path):
        pom = tmp_path / "pom.xml"
        pom.write_text(
            "<project><build><plugins><plugin/></plugins></build></project>", encoding="utf-8"
        )
        project = detect_maven_project(tmp_path)
        overlay = write_overlay_pom(project)
        assert "pitest-maven" in overlay.read_text(encoding="utf-8")
        assert "pitest" not in pom.read_text(encoding="utf-8")  # 원본 불변

    def test_assert_추출은_중첩_괄호를_통째로_잡는다(self):
        stmts = extract_assert_statements(
            "assertThrows(IllegalArgumentException.class, () -> calc.divide(1, 0));"
        )
        assert stmts == ["assertThrows(IllegalArgumentException.class, () -> calc.divide(1, 0))"]
