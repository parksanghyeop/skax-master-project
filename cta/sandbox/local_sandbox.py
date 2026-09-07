"""로컬 실행 샌드박스 — 이 PC의 JDK·Maven으로 같은 명령을 돈다. **기본 실행 장치**다(ADR-0022).

ADR-0019에서 `--fast` 전용으로 들어왔고, ADR-0022로 기본값이 됐다. 격리는 없다: 생성된 테스트가
호스트 JVM에서 돌고 네트워크도 차단되지 않는다. 그래서 화면에 안내 한 줄을 찍고, 격리가 필요한
곳(남의 코드·CI)은 `--runner docker`를 쓰게 한다.
왜 필요한가: Docker 준비 단계(이미지 + go-offline + 예열)가 첫 실행 5분, 매 실행 수십 초의 비용이다.
자기 PC의 신뢰하는 코드베이스에서 빠르게 돌리고 싶을 때 쓴다.

DockerSandbox와 같은 run() 시그니처(Sandbox 프로토콜)라 어댑터(runner·writer·coverage·mutation·
gates)는 변경 없이 둘 다 쓴다. 차이는 세 가지뿐이다.
  - image는 무시한다(호스트 도구 사용)
  - 컨테이너 경로(/work, /m2repo)는 mounts로 호스트 경로로 바꾼다
  - `-o`(오프라인)와 `-Dmaven.repo.local=…`을 뺀다 — 사용자의 ~/.m2를 그대로 쓰고 없는 의존성은
    Maven이 내려받게 한다. 준비 단계를 생략할 수 있는 이유이자 속도의 원천이다
층: sandbox.
"""

import re
import shutil
import subprocess

from cta.sandbox.docker_sandbox import (
    DEFAULT_TIMEOUT_SECONDS,
    TIMEOUT_EXIT_CODE,
    Mount,
    SandboxResult,
    _to_text,
)

# 샌드박스 전용 인자 — 로컬에서는 의미가 없거나(캐시 마운트) 해롭다(오프라인이면 의존성을 못 받는다)
_OFFLINE_FLAG = "-o"
_LOCAL_REPO_PREFIX = "-Dmaven.repo.local="


def translate_paths(args: list[str], mounts: list[Mount]) -> list[str]:
    """인자 안의 컨테이너 경로를 호스트 경로로 바꾼다 — 긴 경로부터, 경계(끝 또는 '/')에서만."""
    ordered = sorted(mounts, key=lambda m: len(m.container_path), reverse=True)
    out = []
    for arg in args:
        for m in ordered:
            pattern = re.escape(m.container_path) + r"(?=/|$)"
            arg = re.sub(pattern, lambda _match, host=m.host_path: host, arg)
        out.append(arg)
    return out


def strip_sandbox_only_flags(args: list[str]) -> list[str]:
    """`-o`와 `-Dmaven.repo.local=…`을 제거한다(위 모듈 설명 참조)."""
    return [a for a in args if a != _OFFLINE_FLAG and not a.startswith(_LOCAL_REPO_PREFIX)]


class LocalSandbox:
    """호스트에서 명령을 실행한다 (Sandbox 프로토콜 구현, 격리 없음).

    실패 시 동작: 명령 실패는 exit_code로 전달(예외 아님), 시간 초과는 TIMEOUT_EXIT_CODE.
    실행 파일(mvn)이 PATH에 없으면 'mvn'을 담은 FileNotFoundError — 오류 안내가 알아본다.
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
        del image, network_enabled  # 로컬 실행에는 이미지도, 네트워크 차단도 없다
        argv = strip_sandbox_only_flags(translate_paths(command, mounts))
        executable = shutil.which(argv[0])  # Windows에서는 mvn.cmd로 풀린다
        if executable is None:
            raise FileNotFoundError(
                f"{argv[0]} 실행 파일을 찾을 수 없다 — 이 PC에서 실행하려면(기본) "
                "Maven과 JDK가 PATH에 있어야 한다. 격리 실행은 --runner docker"
            )
        cwd = translate_paths([workdir], mounts)[0]
        try:
            proc = subprocess.run(
                [executable, *argv[1:]],
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as e:
            partial = _to_text(e.stdout) + _to_text(e.stderr)
            return SandboxResult(
                exit_code=TIMEOUT_EXIT_CODE,
                output=f"{partial}\n[로컬 실행 시간 초과: {timeout_seconds}초]",
            )
        return SandboxResult(exit_code=proc.returncode, output=proc.stdout + proc.stderr)
