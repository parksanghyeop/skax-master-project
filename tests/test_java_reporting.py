"""Java 어댑터의 보고용 파싱 — 실패 테스트 해석, 회차 요약, assert 전후 비교, 변경 단서.

전부 문자열·파일 트리만으로 도는 결정적 검사다(R2). 시나리오의 화면 문구
("기대 0, 실제 null", "바뀌기 전/후 … 점", "예외가 나는지 확인하는 테스트가 통째로 삭제됨")가
여기서 나온다.
"""

import subprocess
from pathlib import Path

from cta.adapters.java.assert_report import (
    compare_test_asserts,
    describe,
    render_changes,
    strictness,
)
from cta.adapters.java.changes import GitChangeExtractor, ReferencingTestLocator
from cta.adapters.java.failures import (
    compile_errors,
    count_tests_run,
    describe_attempt,
    parse_failed_tests,
)
from cta.adapters.java.gates import AssertIntegrityGate, snapshot_baseline
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.parsing import access_modifier, parse_methods, parse_target, strip_methods
from cta.adapters.java.regression import BugReproductionGate
from cta.core.ports import RunResult

SUREFIRE_FAIL = """\
[INFO] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0
[ERROR] Failures:
[ERROR]   PricingCalculatorTest.calculate_emptyItems_returnsZero:19 expected: <0> but was: <null>
[INFO] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0
"""


class TestFailureParsing:
    def test_실패_테스트의_이름_기대_실제를_뽑는다(self):
        failed = parse_failed_tests(SUREFIRE_FAIL)
        assert len(failed) == 1
        assert failed[0].name == "calculate_emptyItems_returnsZero"
        assert (failed[0].expected, failed[0].actual) == ("0", "null")

    def test_실행_테스트_수는_합계_줄이다(self):
        assert count_tests_run(SUREFIRE_FAIL) == 3
        assert count_tests_run("") == 0

    def test_회차_요약_컴파일_실행_통과(self):
        write = "쓰기 완료: x — 컴파일 실패:\n[ERROR] /work/X.java:[10,5] cannot find symbol\n"
        assert describe_attempt(write, "").startswith("컴파일 실패 1건 — cannot find symbol")
        assert compile_errors(write) == ["cannot find symbol"]
        assert describe_attempt("쓰기 완료 — 컴파일 성공", "실패\n" + SUREFIRE_FAIL) == (
            "실행 실패 1건 — 기대 0, 실제 null"
        )
        assert describe_attempt("쓰기 완료", "통과\nTests run: 9") == "전체 통과"


BEFORE = """\
class T {
    @Test
    void applyDiscount_goldMember_appliesRate() {
        assertEquals(new BigDecimal("8500"), result);
    }

    @Test
    void applyDiscount_negativeAmount_throws() {
        assertThrows(IllegalArgumentException.class, () -> service.applyDiscount(o, c, false));
    }
}
"""
AFTER = """\
class T {
    @Test
    void applyDiscount_goldMember_appliesRate() {
        assertNotNull(result);
    }
}
"""


class TestAssertReport:
    def test_완화와_삭제를_테스트_메서드_단위로_보고한다(self):
        changes = compare_test_asserts(BEFORE, AFTER)
        names = [c.test_name for c in changes]
        assert names == [
            "applyDiscount_goldMember_appliesRate",
            "applyDiscount_negativeAmount_throws",
        ]
        text = render_changes(changes)
        assert '바뀌기 전 : 결과가 정확히 new BigDecimal("8500")인지 확인   (4점)' in text
        assert "바뀐 후   : 결과가 null이 아닌지만 확인   (1점)" in text
        assert "예외가 나는지 확인하는 테스트가 통째로 삭제됨" in text

    def test_점수표는_고정값이다(self):
        assert strictness("assertEquals(1, x)") == 4
        assert strictness("assertNotNull(x)") == 1
        assert describe("assertThrows(IllegalStateException.class, () -> f())") == (
            "IllegalStateException 예외가 나는지 확인"
        )

    def test_새_테스트_추가는_변화가_아니다(self):
        assert (
            compare_test_asserts(AFTER, AFTER + "\nclass U { @Test void n() { assertTrue(x); } }")
            == []
        )


def _project(tmp_path: Path):
    main = tmp_path / "src" / "main" / "java"
    test = tmp_path / "src" / "test" / "java"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (test / "T.java").write_text(BEFORE, encoding="utf-8")
    return detect_maven_project(tmp_path)


class TestAuthorizedAsserts:
    def test_사람이_허용한_테스트만_assert_변경이_통과한다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        # goldMember의 기대값만 바꿈(사람이 허용) — negativeAmount는 그대로
        changed = BEFORE.replace('new BigDecimal("8500")', 'new BigDecimal("9000")')
        (project.root / "src/test/java/T.java").write_text(changed, encoding="utf-8")
        assert AssertIntegrityGate(project, baseline).check().passed is False
        allowed = AssertIntegrityGate(
            project, baseline, authorized_tests={"applyDiscount_goldMember_appliesRate"}
        )
        assert allowed.check().passed is True

    def test_허용_목록_밖_assert는_여전히_보호된다(self, tmp_path):
        project = _project(tmp_path)
        baseline = snapshot_baseline(project)
        (project.root / "src/test/java/T.java").write_text(AFTER, encoding="utf-8")
        gate = AssertIntegrityGate(
            project, baseline, authorized_tests={"applyDiscount_goldMember_appliesRate"}
        )
        result = gate.check()
        assert result.passed is False
        assert "negativeAmount" in result.reason


class TestParsingHelpers:
    def test_FQN_클래스와_메서드_목록을_읽는다(self):
        assert parse_target("com.example.OrderService#a,b") == ("OrderService", "a,b")
        assert parse_methods("a, b") == ["a", "b"]
        assert parse_methods("") == []

    def test_접근_제어자와_메서드_제거(self):
        assert access_modifier("    public int f() {") == "public"
        assert access_modifier("    int f() {") == "package"
        stripped = strip_methods(BEFORE, {"applyDiscount_negativeAmount_throws"})
        assert "negativeAmount" not in stripped and "goldMember" in stripped


class _SwapRunner:
    """실행 시점의 소스 내용에 따라 결과를 내는 러너 — 바꿔 끼우기·복구를 검증한다."""

    def __init__(self, path: Path):
        self._path = path
        self.seen: list[str] = []

    def run(self, selector: str) -> RunResult:
        text = self._path.read_text(encoding="utf-8")
        self.seen.append(text)
        return RunResult(passed="fixed" in text, summary="")


class TestRegressionGate:
    def test_수정_전_코드에서_실패하면_통과이고_파일은_복구된다(self, tmp_path):
        project = _project(tmp_path)
        src = project.root / "src/main/java/A.java"
        src.write_text("fixed", encoding="utf-8")
        runner = _SwapRunner(src)
        gate = BugReproductionGate(project, runner, {"src/main/java/A.java": "buggy"}, "ATest")
        result = gate.check()
        assert result.passed is True
        assert runner.seen == ["buggy"]  # 수정 전 코드로 실행됐다
        assert src.read_text(encoding="utf-8") == "fixed"  # 원상 복구

    def test_수정_전_코드에서도_통과하면_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        src = project.root / "src/main/java/A.java"
        src.write_text("fixed", encoding="utf-8")
        gate = BugReproductionGate(
            project, _SwapRunner(src), {"src/main/java/A.java": "fixed too"}, "ATest"
        )
        result = gate.check()
        assert result.passed is False
        assert "수정 전 코드에서도" in result.reason

    def test_수정_전_코드가_없으면_측정_불가로_탈락한다(self, tmp_path):
        project = _project(tmp_path)
        gate = BugReproductionGate(project, _SwapRunner(tmp_path), {"x": None}, "ATest")
        assert gate.check().passed is False


JAVA_V1 = """\
package com.example;

public class Calc {
    public int add(int a, int b) {
        // 더한다
        return a + b;
    }

    private int helper() {
        return 1;
    }
}
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


class TestChangeClues:
    def _repo(self, tmp_path: Path) -> Path:
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        src = tmp_path / "src" / "main" / "java" / "com" / "example"
        src.mkdir(parents=True)
        (src / "Calc.java").write_text(JAVA_V1, encoding="utf-8")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "v1")
        return src / "Calc.java"

    def test_주석만_바뀐_변경과_커밋_메시지_이슈_번호를_뽑는다(self, tmp_path):
        java = self._repo(tmp_path)
        java.write_text(JAVA_V1.replace("// 더한다", "// 두 수를 더한다"), encoding="utf-8")
        _git(tmp_path, "commit", "-q", "-am", "fix: 주석 정리 (#12)")
        change_set = GitChangeExtractor(detect_maven_project(tmp_path), "HEAD~1").extract()
        assert change_set.commit_message.startswith("fix: 주석 정리")
        assert change_set.issue_refs == ("#12",)
        [sym] = change_set.symbols
        assert sym.target == "Calc#add"
        assert sym.comment_only is True
        assert sym.file_rel == "src/main/java/com/example/Calc.java"
        assert sym.change_line == 5

    def test_접근_제어자_변경을_감지하고_수정_전_소스를_꺼낸다(self, tmp_path):
        java = self._repo(tmp_path)
        java.write_text(
            JAVA_V1.replace("private int helper()", "public int helper()"), encoding="utf-8"
        )
        extractor = GitChangeExtractor(detect_maven_project(tmp_path))
        change_set = extractor.extract()
        [sym] = change_set.symbols
        assert sym.signature_changed is True
        assert sym.access_changed is True
        assert sym.comment_only is False
        old = extractor.old_main_sources(change_set)
        assert old["src/main/java/com/example/Calc.java"] == JAVA_V1

    def test_참조_파싱으로_검증_테스트를_찾는다(self, tmp_path):
        self._repo(tmp_path)
        test = tmp_path / "src" / "test" / "java"
        test.mkdir(parents=True)
        (test / "CalcTest.java").write_text("class CalcTest { void t() { new Calc().add(1, 2); } }")
        (test / "OtherTest.java").write_text("class OtherTest { void t() { helper(); } }")
        locator = ReferencingTestLocator(detect_maven_project(tmp_path))
        assert locator.find("Calc#add") == ["CalcTest"]
        assert locator.find("Calc#helper") == []


def test_실패_요약_줄이_없으면_합계_줄로_규모를_알린다():
    out = "실패\n[ERROR] Tests run: 20, Failures: 0, Errors: 2, Skipped: 0, Time elapsed: 1 s"
    assert (
        describe_attempt("쓰기 완료 — 컴파일 성공", out) == "실행 실패 — 20개 중 실패 0건, 오류 2건"
    )


def test_커버리지_실측은_이전_실행_기록을_덧붙이지_않는다():
    # jacoco.exec append 기본값이 true라 앞선 실행의 기록이 섞이면 COVERS·커버리지 게이트가 틀린다
    from cta.adapters.java.coverage import coverage_command

    command = coverage_command("SomeTest")
    assert "-Djacoco.append=false" in command
    assert "-Dmaven.test.failure.ignore=true" in command  # 깨진 테스트도 실행 기록은 남긴다
