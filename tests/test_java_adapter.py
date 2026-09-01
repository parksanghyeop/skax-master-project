"""Java 어댑터(adapters/java)의 단위 테스트 — Docker 없이 돈다.

샌드박스를 스텁으로 바꿔, M1의 안전 불변식을 검증한다:
빈 selector 거부(R5), 실행 단계의 네트워크 차단·오프라인 플래그·캐시 읽기 전용.
"""

import pytest

from adapters.java.maven import NotAMavenProjectError, detect_maven_project
from adapters.java.runner import JavaTestRunner
from core.ports import EmptySelectorError
from sandbox.docker_sandbox import SandboxResult


class StubSandbox:
    """호출 인자를 기록하고 준비된 결과를 차례로 돌려주는 샌드박스 대역."""

    def __init__(self, results: list[SandboxResult]):
        self._results = list(results)
        self.runs: list[dict] = []

    def run(self, **kwargs) -> SandboxResult:
        self.runs.append(kwargs)
        return self._results.pop(0)


def _project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return detect_maven_project(tmp_path)


class TestDetectMavenProject:
    def test_pom이_있으면_루트를_돌려준다(self, tmp_path):
        project = _project(tmp_path)
        assert project.root == tmp_path.resolve()
        assert project.test_source_dir == tmp_path.resolve() / "src" / "test" / "java"

    def test_pom이_없으면_거부한다(self, tmp_path):
        with pytest.raises(NotAMavenProjectError):
            detect_maven_project(tmp_path)


class TestJavaTestRunnerSafety:
    def test_빈_selector는_실행_전에_거부한다(self, tmp_path):
        sandbox = StubSandbox([])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        with pytest.raises(EmptySelectorError):
            runner.run("  ")
        assert sandbox.runs == []  # 샌드박스에 도달조차 하면 안 된다

    def test_예열_selector도_빈_값이면_거부한다(self, tmp_path):
        sandbox = StubSandbox([])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        with pytest.raises(EmptySelectorError):
            runner.prepare("")

    def test_실행_단계는_네트워크_차단_오프라인_캐시읽기전용이다(self, tmp_path):
        sandbox = StubSandbox([SandboxResult(exit_code=0, output="Tests run: 2, Failures: 0")])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        result = runner.run("CalculatorTest")

        assert result.passed is True
        (call,) = sandbox.runs
        assert call["network_enabled"] is False
        assert "-o" in call["command"]
        assert "-Dtest=CalculatorTest" in call["command"]
        m2_mount = next(m for m in call["mounts"] if m.container_path == "/m2repo")
        assert m2_mount.read_only is True

    def test_준비_단계는_네트워크를_켠다(self, tmp_path):
        sandbox = StubSandbox([SandboxResult(0, "go-offline ok"), SandboxResult(0, "Tests run: 2")])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        runner.prepare("CalculatorTest")

        assert [c["network_enabled"] for c in sandbox.runs] == [True, True]
        assert "dependency:go-offline" in sandbox.runs[0]["command"]
        # 예열: go-offline이 빠뜨린 의존성을 실제 실행으로 채운다(v4 6.3)
        assert "-Dtest=CalculatorTest" in sandbox.runs[1]["command"]

    def test_go_offline이_실패하면_예열을_건너뛴다(self, tmp_path):
        sandbox = StubSandbox([SandboxResult(1, "다운로드 실패")])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        result = runner.prepare("CalculatorTest")
        assert result.exit_code == 1
        assert len(sandbox.runs) == 1


class TestJavaTestRunnerResults:
    def test_실패하면_요약에_출력_끝부분이_담긴다(self, tmp_path):
        output = "앞부분\n" * 50 + "Tests run: 3, Failures: 1\n[ERROR] expected 7 but was 8"
        sandbox = StubSandbox([SandboxResult(1, output)])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        result = runner.run("CalculatorTest")

        assert result.passed is False
        assert "Tests run: 3, Failures: 1" in result.summary
        assert "expected 7 but was 8" in result.summary

    def test_통과하면_통계_줄만_요약한다(self, tmp_path):
        output = "긴 로그\n" * 100 + "Tests run: 2, Failures: 0, Errors: 0"
        sandbox = StubSandbox([SandboxResult(0, output)])
        runner = JavaTestRunner(_project(tmp_path), sandbox, tmp_path / "m2")
        result = runner.run("CalculatorTest")

        assert result.passed is True
        assert result.summary == "Tests run: 2, Failures: 0, Errors: 0"
