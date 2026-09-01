"""M1 관문 통합 테스트 — 실제 Docker가 필요하다 (marker: docker).

기본 pytest 실행에서는 제외된다(M0 관문 "Docker 없이 통과" 유지).
실행: pytest -m docker  — 관문: 네트워크 차단 컨테이너에서 mvn -o test 통과.
"""

from pathlib import Path

import pytest

from adapters.java.maven import detect_maven_project
from adapters.java.runner import JavaTestRunner
from sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = REPO_ROOT / "examples" / "demo"
# 캐시를 리포 밖이 아니라 examples 옆에 두는 이유: 준비-실행 단계가 같은 경로를
# 공유해야 하고, 개발자가 지워서 처음부터 재현하기 쉬운 위치여야 한다. gitignore 대상.
M2_CACHE = REPO_ROOT / ".cta" / "m2repo-demo"


@pytest.mark.docker
def test_M1_관문_준비_후_네트워크_차단_실행이_통과한다():
    project = detect_maven_project(DEMO_PROJECT)
    runner = JavaTestRunner(project, DockerSandbox(), M2_CACHE)

    prepared = runner.prepare("CalculatorTest")
    assert prepared.exit_code == 0, f"준비 단계 실패:\n{prepared.output[-2000:]}"

    result = runner.run("CalculatorTest")
    assert result.passed is True, f"오프라인 실행 실패:\n{result.summary}"
    assert "Tests run: 2" in result.summary
