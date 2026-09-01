"""Java 테스트를 Docker 샌드박스에서 준비·실행하는 어댑터 (core TestRunner 포트 구현).

v4 6.3의 2단계 실행을 구현한다:
  1) prepare — 네트워크 연결 상태에서 의존성 내려받기(go-offline) + 예열 실행
  2) run — 네트워크 차단 + 캐시 읽기 전용 마운트로 지정한 테스트만 실행
층: adapters/java. core는 이 파일의 존재를 모른다(R1).
"""

from pathlib import Path

from adapters.java.maven import MavenProject
from core.ports import EmptySelectorError, RunResult
from core.textlimit import clip
from sandbox.docker_sandbox import DockerSandbox, Mount, SandboxResult

# Maven+JDK 공식 이미지. JDK 21: 예제 프로젝트의 컴파일 대상과 일치시킨 선택.
MAVEN_IMAGE = "maven:3.9-eclipse-temurin-21"

# 컨테이너 안 고정 경로. 호스트 경로는 실행 시 마운트로 연결된다.
CONTAINER_WORKDIR = "/work"
CONTAINER_M2_REPO = "/m2repo"

# 실패 시 요약에 남길 출력 꼬리 줄 수. 원인(컴파일 오류·assert 실패)이 대개 끝에 있다.
FAILURE_TAIL_LINES = 30


def _validate_selector(selector: str) -> str:
    # 결정적 안전장치(R2·R5): 빈 selector = 전체 테스트 실행이므로 무조건 거부.
    # 왜 LLM을 안 쓰나: 문자열 검사 하나로 판정된다 — 판단이 필요 없다.
    if not selector.strip():
        raise EmptySelectorError("빈 selector — 전체 테스트 실행은 금지다(R5)")
    return selector.strip()


def _summarize(output: str, passed: bool) -> str:
    """mvn 출력에서 모델이 읽을 요약을 뽑는다.

    통과: 테스트 통계 줄("Tests run: ...")만.
    실패: 통계 줄 + 출력 꼬리(원인이 대개 끝에 있으므로). 길이 상한 적용.
    """
    lines = output.splitlines()
    stats = [ln for ln in lines if "Tests run:" in ln]
    if passed:
        body = "\n".join(stats) or "통과 (통계 줄 없음)"
    else:
        tail = lines[-FAILURE_TAIL_LINES:]
        body = "\n".join(stats + ["--- 출력 끝부분 ---"] + tail)
    return clip(body)


class JavaTestRunner:
    """MavenProject의 테스트를 샌드박스에서 실행한다 (TestRunner 포트 구현).

    입력: project — 탐지된 Maven 프로젝트, sandbox — 실행 장치,
      m2_cache_dir — 의존성 캐시를 둘 호스트 디렉터리(준비·실행 단계가 공유).
    실패 시 동작: 빈 selector는 EmptySelectorError(R5). 테스트 실패·빌드 실패는
      예외가 아니라 passed=False 결과다.
    """

    def __init__(
        self, project: MavenProject, sandbox: DockerSandbox, m2_cache_dir: str | Path
    ) -> None:
        self._project = project
        self._sandbox = sandbox
        self._m2_cache_dir = Path(m2_cache_dir)

    def _mvn(self, extra: list[str]) -> list[str]:
        # -B: 로그의 대화형 장식 제거. repo.local: 캐시를 마운트 지점으로 고정.
        return ["mvn", "-B", f"-Dmaven.repo.local={CONTAINER_M2_REPO}"] + extra

    def prepare(self, warmup_selector: str) -> SandboxResult:
        """준비 단계(네트워크 연결): 의존성을 캐시에 내려받고 예열한다.

        왜 예열(실제 테스트 1회 실행)이 필요한가: go-offline이 일부 의존성
        (surefire 실행기 등)을 빠뜨리는 것으로 알려져 있다(v4 6.3). 실제로 한 번
        돌려야 캐시가 완성된다. warmup_selector에도 R5(빈 selector 금지)를 적용한다.
        """
        selector = _validate_selector(warmup_selector)
        self._m2_cache_dir.mkdir(parents=True, exist_ok=True)
        mounts = [
            Mount(str(self._project.root), CONTAINER_WORKDIR),
            Mount(str(self._m2_cache_dir), CONTAINER_M2_REPO),  # 준비 단계는 쓰기 가능
        ]
        result = self._sandbox.run(
            image=MAVEN_IMAGE,
            command=self._mvn(["dependency:go-offline"]),
            mounts=mounts,
            workdir=CONTAINER_WORKDIR,
            network_enabled=True,
        )
        if result.exit_code != 0:
            return result
        # 예열은 커버리지 계측(JaCoCo)까지 포함해 돌린다 — 오프라인 커버리지 수집
        # (coverage.py)과 M6 커버리지 게이트가 쓸 플러그인을 캐시에 채우기 위해서.
        from adapters.java.coverage import JACOCO_PLUGIN

        return self._sandbox.run(
            image=MAVEN_IMAGE,
            command=self._mvn(
                [
                    f"{JACOCO_PLUGIN}:prepare-agent",
                    "test",
                    f"-Dtest={selector}",
                    f"{JACOCO_PLUGIN}:report",
                ]
            ),
            mounts=mounts,
            workdir=CONTAINER_WORKDIR,
            network_enabled=True,
        )

    def run(self, selector: str) -> RunResult:
        """실행 단계(네트워크 차단): 지정한 테스트만 돌린다.

        -o(오프라인)와 캐시 읽기 전용 마운트로 "인터넷 끊긴 방" 원칙(v4 6.3)을
        지킨다. prepare를 먼저 하지 않았으면 의존성 부족으로 실패 결과가 나온다.
        """
        validated = _validate_selector(selector)
        mounts = [
            Mount(str(self._project.root), CONTAINER_WORKDIR),
            # 왜 읽기 전용: 실행 단계에서 캐시가 변하면 준비 단계의 보증이 깨진다.
            Mount(str(self._m2_cache_dir), CONTAINER_M2_REPO, read_only=True),
        ]
        result = self._sandbox.run(
            image=MAVEN_IMAGE,
            command=self._mvn(["-o", "test", f"-Dtest={validated}"]),
            mounts=mounts,
            workdir=CONTAINER_WORKDIR,
            network_enabled=False,
        )
        passed = result.exit_code == 0
        return RunResult(passed=passed, summary=_summarize(result.output, passed))
