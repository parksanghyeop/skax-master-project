"""커버리지 게이트 탈락 사유의 줄 원문 첨부(describe_source_lines) 테스트.

왜 필요한가: 줄 번호만 주면 모델이 빠진 경로를 알 수 없어 같은 테스트를 반복한다(2026-09-13 실측).
"""

from cta.adapters.java.gates import describe_source_lines
from cta.adapters.java.maven import detect_maven_project

SRC = """\
package a;
public class Calc {
    public int f(int x) {
        if (x < 0) {
            throw new IllegalArgumentException("neg");
        }
        return x * 2;
    }
}
"""


def test_줄_번호에_소스_원문을_붙이고_없는_줄은_번호만_남긴다(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    main = tmp_path / "src" / "main" / "java" / "a"
    main.mkdir(parents=True)
    (main / "Calc.java").write_text(SRC, encoding="utf-8")
    render = describe_source_lines(detect_maven_project(tmp_path), "Calc.java")
    assert render([7, 4]) == "7 `return x * 2;` · 4 `if (x < 0) {`"
    assert render([99]) == "99"
    assert render([]) == "(없음)"


def test_소스_파일을_못_찾으면_번호만_남긴다(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    render = describe_source_lines(detect_maven_project(tmp_path), "Nope.java")
    assert render([1, 2]) == "1 · 2"
