"""Java 파싱·유사 테스트 검색·assert 검사(adapters/java)의 단위 테스트 — Docker 불필요."""

from pathlib import Path

from adapters.java.maven import detect_maven_project
from adapters.java.parsing import extract_methods
from adapters.java.quality import AssertCountChecker, count_asserts
from adapters.java.similar import JavaSimilarTestFinder

MAIN_SOURCE = """\
package com.example;

public class Calc {
    public int add(int a, int b) {
        return a + b;
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("no");
        }
        return a / b;
    }
}
"""

TEST_SOURCE = """\
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


def _demo_project(tmp_path: Path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    main = tmp_path / "src" / "main" / "java" / "com" / "example"
    test = tmp_path / "src" / "test" / "java" / "com" / "example"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    (main / "Calc.java").write_text(MAIN_SOURCE, encoding="utf-8")
    (test / "CalcTest.java").write_text(TEST_SOURCE, encoding="utf-8")
    return detect_maven_project(tmp_path)


class TestExtractMethods:
    def test_이름_파라미터수_예외유무를_뽑는다(self):
        methods = {m.name: m for m in extract_methods(MAIN_SOURCE)}
        assert methods["add"].param_count == 2
        assert methods["add"].uses_exception is False
        assert methods["divide"].param_count == 2
        assert methods["divide"].uses_exception is True

    def test_제어문은_메서드로_오인하지_않는다(self):
        # 회귀: `if (b == 0) {`가 이름 "if"인 메서드로 잡히던 오탐 (파일 모드에서 발견)
        source = """\
public class C {
    public int f(int b) {
        if (b == 0) {
            return 0;
        } else if (b > 1) {
            return 2;
        }
        while (b < 0) { b++; }
        for (int i = 0; i < b; i++) { b--; }
        switch (b) { default: break; }
        return b;
    }
}
"""
        assert [m.name for m in extract_methods(source)] == ["f"]

    def test_테스트_어노테이션을_인식한다(self):
        methods = [m for m in extract_methods(TEST_SOURCE) if m.is_test]
        assert [m.name for m in methods] == ["add_twoPositives_returnsSum"]


class TestProjectHelpers:
    def test_package_선언을_읽는다(self):
        from adapters.java.parsing import read_package

        assert read_package(MAIN_SOURCE) == "com.example"
        assert read_package("public class NoPkg {}") == ""

    def test_기존_테스트_클래스를_찾는다(self, tmp_path):
        from adapters.java.maven import find_existing_test_class

        project = _demo_project(tmp_path)
        assert find_existing_test_class(project) == "CalcTest"

    def test_테스트가_없으면_None이다(self, tmp_path):
        from adapters.java.maven import detect_maven_project, find_existing_test_class

        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        assert find_existing_test_class(detect_maven_project(tmp_path)) is None


class TestSimilarTestFinder:
    def test_모양이_닮은_기존_테스트를_발췌한다(self, tmp_path):
        finder = JavaSimilarTestFinder(_demo_project(tmp_path))
        answer = finder.find("Calc#divide")
        # add(2개 인자)가 divide(2개 인자)의 최선 본보기다 — 예외 유무만 다르다
        assert "본보기" in answer
        assert "add_twoPositives_returnsSum" in answer

    def test_형식이_틀리면_안내_문자열이다(self, tmp_path):
        finder = JavaSimilarTestFinder(_demo_project(tmp_path))
        assert "대상 없음" in finder.find("NoSuchClass#x")


class TestAssertCountChecker:
    def test_새_테스트에_assert가_있으면_통과(self, tmp_path):
        project = _demo_project(tmp_path)
        checker = AssertCountChecker(project)  # 기준선: 새 파일이 생기기 전
        new_file = project.test_source_dir / "com" / "example" / "NewTest.java"
        new_file.write_text("@Test void t() { assertEquals(1, 1); }", encoding="utf-8")
        assert checker.check(str(new_file)).startswith("통과")

    def test_새_테스트에_assert가_없으면_탈락(self, tmp_path):
        project = _demo_project(tmp_path)
        checker = AssertCountChecker(project)
        new_file = project.test_source_dir / "com" / "example" / "EmptyTest.java"
        new_file.write_text("@Test void t() { new Calc().add(1, 2); }", encoding="utf-8")
        assert checker.check(str(new_file)).startswith("탈락")

    def test_기존_테스트의_assert가_줄면_탈락(self, tmp_path):
        project = _demo_project(tmp_path)
        existing = project.test_source_dir / "com" / "example" / "CalcTest.java"
        checker = AssertCountChecker(project)  # 기준선: assert 1개
        existing.write_text(
            TEST_SOURCE.replace("assertEquals(7, new Calc().add(3, 4));", ""), encoding="utf-8"
        )
        verdict = checker.check(str(existing))
        assert verdict.startswith("탈락")
        assert "사람 확인" in verdict

    def test_count_asserts는_호출형과_문형을_센다(self):
        assert count_asserts("assertEquals(1,1); assertThrows(E.class, r); x.compute();") == 2
