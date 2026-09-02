"""M1 관문 통합 테스트 — 실제 Docker가 필요하다 (marker: docker).

기본 pytest 실행에서는 제외된다(M0 관문 "Docker 없이 통과" 유지).
실행: pytest -m docker  — 관문: 네트워크 차단 컨테이너에서 mvn -o test 통과.
"""

from pathlib import Path

import pytest

from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.runner import JavaTestRunner
from cta.sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = REPO_ROOT / "examples" / "demo"
M2_CACHE = DEMO_PROJECT / ".cta" / "m2repo"  # CLI와 같은 캐시


@pytest.mark.docker
def test_M1_관문_준비_후_네트워크_차단_실행이_통과한다():
    project = detect_maven_project(DEMO_PROJECT)
    runner = JavaTestRunner(project, DockerSandbox(), M2_CACHE)

    prepared = runner.prepare("OrderServiceTest")
    assert prepared.exit_code == 0, f"준비 단계 실패:\n{prepared.output[-2000:]}"

    result = runner.run("OrderServiceTest")
    assert result.passed is True, f"오프라인 실행 실패:\n{result.summary}"
    assert "Tests run: 4" in result.summary
