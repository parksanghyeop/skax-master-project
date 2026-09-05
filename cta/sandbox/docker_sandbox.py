"""Docker 컨테이너에서 명령 한 번을 실행하는 래퍼.

왜 sandbox 층에 있나: 격리(네트워크 차단, 마운트 통제)는 언어와 무관한 공통
관심사다(v4 6.3). 기본값이 네트워크 차단이라는 점이 이 모듈의 핵심 안전장치다.
"""

import subprocess
from dataclasses import dataclass

# 왜 상한이 있나: LLM이 만든 테스트가 무한 루프여도 세션이 잠기지 않게.
# 값 근거: 의존성 내려받기(준비 단계)가 수 분 걸릴 수 있어 넉넉히 10분.
DEFAULT_TIMEOUT_SECONDS = 600

# 시간 초과를 일반 실패와 구분하기 위한 관례적 종료 코드 (GNU timeout과 동일).
TIMEOUT_EXIT_CODE = 124


@dataclass(frozen=True)
class Mount:
    """호스트 디렉터리를 컨테이너에 붙이는 설정.

    read_only=True면 컨테이너가 그 경로에 쓸 수 없다 — 실행 단계에서
    의존성 캐시를 보호하는 데 쓴다(v4 6.3 "읽기 전용으로 마운트").
    """

    host_path: str
    container_path: str
    read_only: bool = False


@dataclass(frozen=True)
class SandboxResult:
    """컨테이너 실행 한 번의 결과. output은 stdout·stderr 합본."""

    exit_code: int
    output: str


def build_run_args(
    image: str,
    command: list[str],
    mounts: list[Mount],
    workdir: str,
    network_enabled: bool = False,
) -> list[str]:
    """`docker run` 인자 목록을 만든다 — 순수 함수라 Docker 없이 검사할 수 있다.

    안전장치 두 가지가 여기서 보장된다(테스트 tests/test_secrets.py가 고정):
    - 네트워크는 기본 차단(`--network none`). 준비 단계(의존성 내려받기)만 명시적으로 켠다(v4 6.3)
    - 호스트 환경변수를 넘기는 `-e`/`--env`/`--env-file`을 쓰지 않는다 — 게이트웨이 키가
      컨테이너(LLM이 만든 코드가 실행되는 곳)로 들어갈 경로를 애초에 두지 않는다(v4 6.6)
    """
    args = ["docker", "run", "--rm"]
    if not network_enabled:
        args += ["--network", "none"]
    for m in mounts:
        spec = f"{m.host_path}:{m.container_path}"
        if m.read_only:
            spec += ":ro"
        args += ["-v", spec]
    return args + ["-w", workdir, image] + command


def _to_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


class DockerSandbox:
    """docker run으로 명령을 실행한다.

    무엇을 하나: 이미지·명령·마운트를 받아 1회용 컨테이너(--rm)에서 돌리고
      종료 코드와 출력을 돌려준다.
    실패 시 동작: 명령 실패는 exit_code로 전달(예외 아님). 시간 초과는
      TIMEOUT_EXIT_CODE로 전달. docker CLI 자체가 없으면 'docker'를 담은 FileNotFoundError를
      던진다 — 환경 문제는 숨기지 않고, 오류 안내가 알아볼 수 있게 한다.
    """

    def run(
        self,
        image: str,
        command: list[str],
        mounts: list[Mount],
        workdir: str,
        network_enabled: bool = False,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> SandboxResult:
        args = build_run_args(image, command, mounts, workdir, network_enabled)

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as e:
            # 왜 변환 함수: TimeoutExpired의 stdout/stderr는 파이썬 버전에 따라
            # text=True여도 bytes로 올 수 있다.
            partial = _to_text(e.stdout) + _to_text(e.stderr)
            return SandboxResult(
                exit_code=TIMEOUT_EXIT_CODE,
                output=f"{partial}\n[샌드박스 시간 초과: {timeout_seconds}초]",
            )
        except FileNotFoundError as e:
            # Windows 원문("[WinError 2] 지정된 파일을 찾을 수 없습니다")에는 'docker'가 없어
            # 오류 안내(cli/hints)가 Docker 문제로 알아보지 못한다 — 무엇을 못 찾았는지 담는다
            raise FileNotFoundError(
                f"docker 실행 파일을 찾을 수 없다 — Docker가 설치돼 있고 PATH에 있는가 ({e})"
            ) from e
        return SandboxResult(exit_code=proc.returncode, output=proc.stdout + proc.stderr)
