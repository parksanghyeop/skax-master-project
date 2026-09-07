"""작성자 지정 의도(ADR-0020 D1)의 단위 테스트 — 전부 Fake, LLM·Docker 없음.

검증: --intent가 분류를 덮어쓰되 주석만 변경은 trivial을 유지하고, --message가 미커밋 변경의
커밋 메시지 자리에 들어가며, resolve --as가 저장된 테스트 상태로 규칙표를 다시 조회한다.
"""

import argparse
import dataclasses
import subprocess
from pathlib import Path

import pytest

from cta.adapters.fake import FakeTestRunner
from cta.adapters.java.changes import GitChangeExtractor
from cta.adapters.java.maven import detect_maven_project
from cta.cli import resolve_cmd
from cta.cli.escalations import Escalation, make_id
from cta.cli.resolve_cmd import stated_intent_decision
from cta.core.pipeline.maintain import AUTHOR_INTENTS, analyze_changes, with_author_intent
from cta.core.pipeline.models import (
    ACTION_CREATE_TEST,
    ACTION_ESCALATE,
    ACTION_NO_ACTION,
    INTENT_BUG_FIX,
    INTENT_REFACTOR,
    INTENT_TRIVIAL,
    INTENT_UNCLEAR,
    TESTS_FAIL,
    TESTS_NONE,
    TESTS_PASS,
    ChangedSymbol,
    ChangeSet,
    Intent,
)

DEAD_CODE = ChangedSymbol(
    target="PricingCalculator#calculate",
    lines_added=2,
    lines_removed=0,
    signature_changed=False,
    diff_excerpt="+ BigDecimal subtotal2 = subtotal.abs();\n+ subtotal2 = subtotal;",
)
COMMENT = ChangedSymbol(
    target="PricingCalculator#toString",
    lines_added=1,
    lines_removed=1,
    signature_changed=False,
    diff_excerpt="- // a\n+ // b",
    comment_only=True,
)
UNCLEAR = Intent(
    category=INTENT_UNCLEAR, analysis="의도를 알 수 없다", confidence=0.4, evidence=("근거",)
)


class _UnclearClassifier:
    def classify(self, change, change_set, memos=""):
        return UNCLEAR


class _NoTests:
    def find(self, target):
        return []


class TestWithAuthorIntent:
    def test_분류를_덮어쓰고_근거_첫_줄에_작성자_지정을_남긴다(self):
        intent = with_author_intent(UNCLEAR, INTENT_BUG_FIX)
        assert intent.category == INTENT_BUG_FIX
        assert intent.confidence == 1.0
        assert intent.evidence[0].startswith("작성자 지정 의도")
        assert intent.evidence[1:] == UNCLEAR.evidence  # LLM 근거·분석은 유지
        assert intent.analysis == UNCLEAR.analysis

    def test_trivial과_unclear는_지정할_수_없다(self):
        assert INTENT_TRIVIAL not in AUTHOR_INTENTS and INTENT_UNCLEAR not in AUTHOR_INTENTS
        with pytest.raises(ValueError):
            with_author_intent(UNCLEAR, INTENT_UNCLEAR)

    def test_analyze_changes에서_주석만_변경은_지정과_무관하게_trivial이다(self):
        change_set = ChangeSet(symbols=[DEAD_CODE, COMMENT])
        analyses = analyze_changes(
            change_set, _UnclearClassifier(), _NoTests(), FakeTestRunner(), author_intent="bug_fix"
        )
        by_target = {a.change.target: a for a in analyses}
        assert by_target[DEAD_CODE.target].intent.category == INTENT_BUG_FIX
        assert by_target[DEAD_CODE.target].decision.kind == ACTION_CREATE_TEST
        assert by_target[COMMENT.target].intent.category == INTENT_TRIVIAL
        assert by_target[COMMENT.target].decision.kind == ACTION_NO_ACTION


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


class TestMessageOverride:
    def test_미커밋_변경에_message를_주면_커밋_메시지_자리에_들어가고_이슈_번호도_뽑힌다(
        self, tmp_path
    ):
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        src = tmp_path / "src" / "main" / "java"
        src.mkdir(parents=True)
        java = src / "Calc.java"
        java.write_text(
            "public class Calc {\n    int f() {\n        return 1;\n    }\n}\n", encoding="utf-8"
        )
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "v1")
        java.write_text(
            "public class Calc {\n    int f() {\n        return 2;\n    }\n}\n", encoding="utf-8"
        )

        project = detect_maven_project(tmp_path)
        plain = GitChangeExtractor(project).extract()
        described = GitChangeExtractor(project, message_override="fix: 반환값 오류 (#77)").extract()

        assert plain.commit_message == ""
        assert described.commit_message == "fix: 반환값 오류 (#77)"
        assert described.issue_refs == ("#77",)


def _ask(tests: list[str], tests_status: str = "", failed: list[dict] | None = None) -> Escalation:
    return Escalation(
        id=make_id("PricingCalculator#calculate"),
        kind="ask",
        target="PricingCalculator#calculate",
        category="unclear",
        confidence=0.4,
        evidence=["커밋 메시지: 없음"],
        analysis="의도를 알 수 없다",
        reason="분류 불확실",
        briefing="지침",
        tests=tests,
        run_summary="",
        failed_tests=failed or [],
        file_rel="src/main/java/PricingCalculator.java",
        change_line=20,
        diff_excerpt="+ x",
        base="HEAD",
        commit_message="",
        created_at="2026-09-04T00:00:00",
        tests_status=tests_status,
    )


class TestStatedIntentDecision:
    def test_버그_수정으로_지정하면_테스트_상태와_무관하게_생성이다(self):
        decision, status = stated_intent_decision(_ask([], TESTS_NONE), INTENT_BUG_FIX)
        assert decision.kind == ACTION_CREATE_TEST and status == TESTS_NONE
        assert decision.briefing.startswith("대상: PricingCalculator#calculate")

    def test_리팩터링인데_테스트_통과면_할_일_없음이다(self):
        decision, _ = stated_intent_decision(_ask(["T"], TESTS_PASS), INTENT_REFACTOR)
        assert decision.kind == ACTION_NO_ACTION

    def test_리팩터링인데_테스트_실패면_여전히_사람_확인이다(self):
        decision, _ = stated_intent_decision(_ask(["T"], TESTS_FAIL), INTENT_REFACTOR)
        assert decision.kind == ACTION_ESCALATE  # 기대값 자동 수정 행은 없다(R3)

    def test_구_파일은_테스트_유무와_실패_유무로_상태를_유추한다(self):
        _, none_status = stated_intent_decision(_ask([]), INTENT_REFACTOR)
        _, pass_status = stated_intent_decision(_ask(["T"]), INTENT_REFACTOR)
        _, fail_status = stated_intent_decision(
            _ask(["T"], failed=[{"name": "t"}]), INTENT_REFACTOR
        )
        assert (none_status, pass_status, fail_status) == (TESTS_NONE, TESTS_PASS, TESTS_FAIL)


class TestResolveAsPassesRunOptions:
    def test_as_경로도_fast_runner_quiet를_run_generation에_넘긴다(self, tmp_path, monkeypatch):
        """검토(2026-09-07)에서 찾은 결함의 회귀 테스트 — --as 경로만 runner_kind·quiet를
        빠뜨려 `--fast`인데도 Docker 샌드박스가 선택됐다(ADR-0019 위반)."""
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        project = detect_maven_project(tmp_path)
        captured: dict = {}

        def fake_run_generation(**kwargs):
            captured.update(kwargs)
            return {"status": "ok", "status_label": "정상 완료", "proposal": ""}

        monkeypatch.setattr(resolve_cmd, "run_generation", fake_run_generation)
        escalation = _ask(tests=[], tests_status=TESTS_NONE)
        # file_rel을 비워 git 조회 없이 new_feature 경로만 본다(Escalation은 frozen)
        escalation = dataclasses.replace(escalation, file_rel="")
        args = argparse.Namespace(
            as_intent="new_feature",
            hint="",
            fast=True,
            runner=None,
            quiet=True,
            non_interactive=True,
        )

        code = resolve_cmd._resolve_as(project, escalation, args)

        assert code == 0
        assert captured["runner_kind"] == "local"
        assert captured["quiet"] is True
        assert captured["fast"] is True
