"""실행 장치 선택 — Docker 샌드박스(기본) 또는 로컬 실행(--fast / --runner local) (ADR-0019).

선택 규칙 한 줄: 명시한 `--runner`가 이기고, 없으면 `--fast`일 때만 local, 아니면 docker.
왜 `--fast`가 local을 뜻하나: 사용자가 "빠르게"라고 한 것은 Docker 준비·실행 비용을 빼 달라는
뜻이었다(2026-09-06). CI처럼 격리는 유지하되 게이트만 줄이고 싶으면 `--fast --runner docker`.
층: sandbox.
"""

from cta.sandbox.docker_sandbox import DockerSandbox, Sandbox
from cta.sandbox.local_sandbox import LocalSandbox

RUNNER_DOCKER = "docker"
RUNNER_LOCAL = "local"
RUNNERS = (RUNNER_DOCKER, RUNNER_LOCAL)

# 로컬 모드를 켤 때 화면에 한 번 찍는 경고 — R6 완화를 사용자가 알고 쓰게 한다
LOCAL_MODE_WARNING = (
    "로컬 실행 모드 — 생성된 테스트가 이 PC의 JVM에서 격리 없이 실행된다(Docker 미사용, ADR-0019). "
    "신뢰하는 코드베이스에서만 쓴다. 격리 실행: --runner docker"
)


def choose_runner(explicit: str | None, fast: bool) -> str:
    """플래그 조합에서 실행 장치 이름을 정한다. 잘못된 이름은 ValueError."""
    if explicit:
        if explicit not in RUNNERS:
            raise ValueError(f"--runner는 {', '.join(RUNNERS)} 중 하나여야 한다: {explicit!r}")
        return explicit
    return RUNNER_LOCAL if fast else RUNNER_DOCKER


def make_sandbox(kind: str) -> Sandbox:
    """이름으로 실행 장치를 만든다."""
    if kind == RUNNER_LOCAL:
        return LocalSandbox()
    if kind == RUNNER_DOCKER:
        return DockerSandbox()
    raise ValueError(f"알 수 없는 실행 장치: {kind!r}")
