"""게이트 ④⑤ 실측 불변식 — 실제 Docker 필요 (marker: docker).

핵심 불변식(phase2 스킬): "assert 없는 100% 커버리지 테스트"는 커버리지 게이트를
속일 수 있어도 **뮤테이션 게이트에서 탈락**해야 한다.
사전 조건: examples/demo의 의존성 캐시가 PIT 예열 포함으로 준비돼 있어야 한다
(캐시 삭제 후 아무 CLI나 실행하면 준비된다).
"""

from pathlib import Path

import pytest

from cta.adapters.java.gates import CoverageGate
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.mutation import MutationGate
from cta.adapters.java.parsing import method_line_spans
from cta.core.gates import GateConfig
from cta.sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "demo"
CACHE = DEMO / ".cta" / "m2repo"

# assert가 하나도 없는 "실행만 하는" 테스트 — 라인은 커버하지만 아무것도 검증 안 함
ASSERTLESS_TEST = """\
package com.example.demo;

import org.junit.jupiter.api.Test;

class CalculatorAssertlessTest {

    @Test
    void add_runsWithoutChecking() {
        Calculator calculator = new Calculator();
        calculator.add(3, 4);
        calculator.add(-1, 1);
    }
}
"""

TEST_PATH = (
    DEMO / "src" / "test" / "java" / "com" / "example" / "demo" / "CalculatorAssertlessTest.java"
)


@pytest.mark.docker
def test_불변식4_assert_없는_테스트는_커버리지를_채워도_뮤테이션에서_탈락한다():
    project = detect_maven_project(DEMO)
    sandbox = DockerSandbox()
    source = (
        DEMO / "src" / "main" / "java" / "com" / "example" / "demo" / "Calculator.java"
    ).read_text(encoding="utf-8")
    span = next(s for s in method_line_spans(source) if s.name == "add")
    add_lines = set(range(span.start_line, span.end_line + 1))
    try:
        TEST_PATH.write_text(ASSERTLESS_TEST, encoding="utf-8")

        coverage = CoverageGate(
            project,
            sandbox,
            CACHE,
            "CalculatorAssertlessTest",
            "Calculator.java",
            add_lines,
            GateConfig(),
        ).check()
        # 실행은 되므로 커버리지는 채워진다 — 커버리지 단독으로는 못 거른다는 증거
        assert coverage.passed is True, coverage.reason

        mutation = MutationGate(
            project,
            sandbox,
            CACHE,
            "com.example.demo.Calculator",
            "com.example.demo.CalculatorAssertlessTest",
            min_killed_ratio=0.5,
            target_method="add",
        ).check()
        # 검증이 없으니 심은 버그를 하나도 못 잡는다 → 탈락해야 한다
        assert mutation.passed is False, mutation.reason
        assert "0개" in mutation.reason or "검출" in mutation.reason
    finally:
        TEST_PATH.unlink(missing_ok=True)
        (DEMO / "pom-cta-pit.xml").unlink(missing_ok=True)


@pytest.mark.docker
def test_진짜_검증이_있는_테스트는_뮤테이션을_통과한다():
    project = detect_maven_project(DEMO)
    sandbox = DockerSandbox()
    mutation = MutationGate(
        project,
        sandbox,
        CACHE,
        "com.example.demo.Calculator",
        "com.example.demo.CalculatorTest",
        min_killed_ratio=0.5,
        target_method="add",  # CalculatorTest는 add를 검증한다
    ).check()
    try:
        assert mutation.passed is True, mutation.reason
    finally:
        (DEMO / "pom-cta-pit.xml").unlink(missing_ok=True)
