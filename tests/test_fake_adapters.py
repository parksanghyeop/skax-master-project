"""Fake 어댑터(adapters/fake.py)와 core 공용 로직의 단위 테스트.

M0 관문 "Java·Docker 없이 pytest 통과"의 실체 — Fake만으로 포트 계약
(빈 selector 거부 R5, 문자열 반환)을 검증한다.
"""

import pytest

from adapters.fake import FakeSourceInspector, FakeTestRunner
from core.ports import EmptySelectorError, RunResult
from core.textlimit import TOOL_OUTPUT_MAX_CHARS, clip


class TestFakeTestRunner:
    def test_빈_selector는_거부한다(self):
        runner = FakeTestRunner()
        with pytest.raises(EmptySelectorError):
            runner.run("")

    def test_공백뿐인_selector도_거부한다(self):
        runner = FakeTestRunner()
        with pytest.raises(EmptySelectorError):
            runner.run("   ")

    def test_등록된_selector는_준비된_결과를_돌려준다(self):
        expected = RunResult(passed=True, summary="1 passed")
        runner = FakeTestRunner({"CalculatorTest": expected})
        assert runner.run("CalculatorTest") == expected
        assert runner.calls == ["CalculatorTest"]

    def test_모르는_selector는_예외가_아니라_실패_결과다(self):
        runner = FakeTestRunner()
        result = runner.run("NoSuchTest")
        assert result.passed is False
        assert "NoSuchTest" in result.summary


class TestFakeSourceInspector:
    def test_등록된_대상은_소스를_돌려준다(self):
        inspector = FakeSourceInspector({"acme.Calc#add": "int add(int a, int b)"})
        assert inspector.inspect("acme.Calc#add") == "int add(int a, int b)"

    def test_없는_대상은_예외가_아니라_안내_문자열이다(self):
        inspector = FakeSourceInspector({"acme.Calc#add": "..."})
        message = inspector.inspect("acme.Calc#sub")
        assert "acme.Calc#sub" in message
        assert "acme.Calc#add" in message  # 모델이 다음 행동을 고르도록 알려진 대상을 함께 준다


class TestClip:
    def test_상한_이하면_그대로다(self):
        assert clip("짧은 출력", limit=100) == "짧은 출력"

    def test_상한을_넘으면_자르고_표식을_붙인다(self):
        text = "x" * 500
        result = clip(text, limit=100)
        assert len(result) <= 100
        assert "잘림" in result
        assert "500" in result  # 전체 길이를 표식에 남긴다

    def test_기본_상한이_적용된다(self):
        text = "y" * (TOOL_OUTPUT_MAX_CHARS + 1000)
        assert len(clip(text)) <= TOOL_OUTPUT_MAX_CHARS
