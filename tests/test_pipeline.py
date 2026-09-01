"""파이프라인(M5) 단위 테스트 — 조치 결정 규칙표·의도 파싱·변경 추출.

변경 추출 테스트는 임시 git 저장소를 만들어 실제 git diff로 검증한다(네트워크 불필요).
"""

import subprocess
from pathlib import Path

from cta.adapters.java.changes import GitChangeExtractor
from cta.adapters.java.maven import detect_maven_project
from cta.core.pipeline.decide import decide
from cta.core.pipeline.models import (
    ACTION_ASK,
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    ACTION_NO_ACTION,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    ChangedSymbol,
    Intent,
)
from cta.llm.intent import parse_intent

CHANGE = ChangedSymbol(
    target="Calc#divide",
    lines_added=3,
    lines_removed=1,
    signature_changed=False,
    diff_excerpt="+...",
)


class TestDecisionTable:
    """규칙표 검증 — 특히 '기대값 자동 수정' 경로가 존재하지 않음을 못박는다(R3)."""

    def test_버그_수정은_테스트_상태와_무관하게_새_테스트다(self):
        for status in (TESTS_PASS, TESTS_FAIL, TESTS_NONE):
            d = decide(CHANGE, Intent("bug_fix", "0 나누기 수정"), status)
            assert d.kind == ACTION_CREATE_TEST

    def test_리팩터링에_테스트_통과면_아무것도_안_한다(self):
        d = decide(CHANGE, Intent("refactor", "이름 정리"), TESTS_PASS)
        assert d.kind == ACTION_NO_ACTION

    def test_리팩터링인데_테스트_실패면_반드시_사람에게_넘긴다(self):
        d = decide(CHANGE, Intent("refactor", "이름 정리"), TESTS_FAIL)
        assert d.kind == ACTION_ESCALATE  # R3: 기대값을 갱신하는 분기는 없다

    def test_리팩터링인데_커버_테스트가_없으면_묻는다(self):
        d = decide(CHANGE, Intent("refactor", "이름 정리"), TESTS_NONE)
        assert d.kind == ACTION_ASK

    def test_불확실_분류는_표를_보지_않고_묻는다(self):
        for status in (TESTS_PASS, TESTS_FAIL, TESTS_NONE):
            assert decide(CHANGE, Intent("unclear", "?"), status).kind == ACTION_ASK

    def test_모르는_분류값도_묻는다(self):
        assert decide(CHANGE, Intent("chore", "?"), TESTS_PASS).kind == ACTION_ASK

    def test_지침서에_분석과_변경_규모가_들어간다(self):
        d = decide(CHANGE, Intent("bug_fix", "0 나누기 경계를 시험하라"), TESTS_NONE)
        assert "0 나누기 경계를 시험하라" in d.briefing
        assert "+3/-1" in d.briefing


class TestParseIntent:
    def test_정상_JSON을_읽는다(self):
        intent = parse_intent('{"category": "bug_fix", "analysis": "경계값 수정"}')
        assert intent.category == "bug_fix"
        assert intent.analysis == "경계값 수정"

    def test_코드_블록에_싸여_있어도_JSON만_건진다(self):
        intent = parse_intent('```json\n{"category": "refactor", "analysis": "정리"}\n```')
        assert intent.category == "refactor"

    def test_파싱_실패는_unclear로_수렴한다(self):
        assert parse_intent("잘 모르겠는데요").category == "unclear"
        assert parse_intent('{"category": "bug_fix"').category == "unclear"

    def test_모르는_분류값은_unclear로_강등한다(self):
        assert parse_intent('{"category": "banana", "analysis": "x"}').category == "unclear"


JAVA_V1 = """\
package com.example;

public class Calc {
    public int add(int a, int b) {
        return a + b;
    }

    public int divide(int a, int b) {
        return a / b;
    }
}
"""

JAVA_V2 = """\
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


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


class TestGitChangeExtractor:
    def test_수정된_메서드를_심볼로_뽑는다(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        src = tmp_path / "src" / "main" / "java" / "com" / "example"
        src.mkdir(parents=True)
        java = src / "Calc.java"
        java.write_text(JAVA_V1, encoding="utf-8")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "v1")
        java.write_text(JAVA_V2, encoding="utf-8")

        changes = GitChangeExtractor(detect_maven_project(tmp_path)).extract()

        assert [c.target for c in changes] == ["Calc#divide"]
        assert changes[0].lines_added == 3
        assert changes[0].lines_removed == 0
        assert "IllegalArgumentException" in changes[0].diff_excerpt

    def test_상위_저장소의_하위_폴더_프로젝트도_경로가_맞는다(self, tmp_path):
        # examples/demo처럼 프로젝트가 더 큰 git 저장소 안에 있는 경우 —
        # --relative가 없으면 diff 경로가 저장소 루트 기준이라 매핑이 빗나간다
        project_dir = tmp_path / "examples" / "demo"
        src = project_dir / "src" / "main" / "java" / "com" / "example"
        src.mkdir(parents=True)
        (project_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
        java = src / "Calc.java"
        java.write_text(JAVA_V1, encoding="utf-8")
        _git(tmp_path, "init", "-q")  # 저장소 루트는 tmp_path — 프로젝트보다 위
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "v1")
        java.write_text(JAVA_V2, encoding="utf-8")

        changes = GitChangeExtractor(detect_maven_project(project_dir)).extract()
        assert [c.target for c in changes] == ["Calc#divide"]

    def test_변경이_없으면_빈_목록이다(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        _git(tmp_path, "init", "-q")
        (tmp_path / "A.txt").write_text("x", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "v1")
        assert GitChangeExtractor(detect_maven_project(tmp_path)).extract() == []
