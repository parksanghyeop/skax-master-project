"""실행 장치 선택 — 로컬 실행(기본) 또는 Docker 샌드박스(--runner docker) (ADR-0022).

선택 규칙 한 줄: 명시한 `--runner`가 이기고, 없으면 항상 local. `--fast`는 실행 장치와 무관하다
(무거운 게이트 생략만 — ADR-0022 결정 2).
왜 로컬이 기본인가: Docker 경로의 비용(Windows 바인드 마운트로 Maven 1회 20~45초, 첫 준비 5분)이
시연·설치 부담의 대부분이었다. 격리가 필요한 곳(남의 코드, CI)은 `--runner docker`로 고른다.
층: sandbox.
"""

from cta.sandbox.docker_sandbox import DockerSandbox, Sandbox
from cta.sandbox.local_sandbox import LocalSandbox

RUNNER_DOCKER = "docker"
RUNNER_LOCAL = "local"
RUNNERS = (RUNNER_DOCKER, RUNNER_LOCAL)

# 로컬 실행일 때 화면에 한 번 찍는 안내 — 기본값이므로 경고가 아니라 정보다.
# 격리가 없다는 사실은 알린다(R6)
LOCAL_MODE_NOTE = (
    "실행: 이 PC의 Maven·JDK (격리 없음 — 생성된 테스트가 사용자 권한으로 돈다). "
    "격리 실행: --runner docker"
)


def choose_runner(explicit: str | None, fast: bool) -> str:
    """플래그 조합에서 실행 장치 이름을 정한다. 잘못된 이름은 ValueError.

    fast는 호환을 위해 받지만 결과에 영향이 없다(ADR-0022 — `--fast`는 게이트 생략만).
    """
    if explicit:
        if explicit not in RUNNERS:
            raise ValueError(f"--runner는 {', '.join(RUNNERS)} 중 하나여야 한다: {explicit!r}")
        return explicit
    return RUNNER_LOCAL


def make_sandbox(kind: str) -> Sandbox:
    """이름으로 실행 장치를 만든다."""
    if kind == RUNNER_LOCAL:
        return LocalSandbox()
    if kind == RUNNER_DOCKER:
        return DockerSandbox()
    raise ValueError(f"알 수 없는 실행 장치: {kind!r}")
