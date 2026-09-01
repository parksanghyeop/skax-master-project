"""Java용 TestWriter 구현 — 테스트 파일 쓰기 + 오프라인 컴파일 검사.

범위 제약(테스트 폴더 밖 쓰기 금지, v4 1절 제약 ④)을 결정적으로 강제한다 —
경로 검사 하나로 판정되므로 LLM 판단을 끼우지 않는다(R2). 컴파일 검사도
네트워크 차단 샌드박스에서 한다(R6). 층: adapters/java.
"""

from pathlib import Path

from adapters.java.maven import MavenProject
from adapters.java.runner import CONTAINER_M2_REPO, CONTAINER_WORKDIR, MAVEN_IMAGE
from sandbox.docker_sandbox import DockerSandbox, Mount

# 컴파일 오류는 대개 출력 끝에 모여 있다 — 요약에 남길 꼬리 줄 수.
COMPILE_TAIL_LINES = 25


class JavaTestWriter:
    """테스트 파일을 쓰고 mvn test-compile(오프라인)로 검사한다 (TestWriter 포트 구현)."""

    def __init__(
        self, project: MavenProject, sandbox: DockerSandbox, m2_cache_dir: str | Path
    ) -> None:
        self._project = project
        self._sandbox = sandbox
        self._m2_cache_dir = Path(m2_cache_dir)

    def write(self, path: str, code: str) -> str:
        resolved = Path(path).resolve()
        test_root = self._project.test_source_dir.resolve()
        # 결정적 범위 검사(R2): 테스트 폴더 밖이면 쓰지 않는다. 파일을 만들기 전에 거른다.
        if not resolved.is_relative_to(test_root):
            return f"거부: 테스트 폴더({test_root}) 밖에는 쓸 수 없다 — 요청 경로: {resolved}"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(code, encoding="utf-8")

        result = self._sandbox.run(
            image=MAVEN_IMAGE,
            command=[
                "mvn",
                "-B",
                "-o",
                f"-Dmaven.repo.local={CONTAINER_M2_REPO}",
                "test-compile",
            ],
            mounts=[
                Mount(str(self._project.root), CONTAINER_WORKDIR),
                Mount(str(self._m2_cache_dir), CONTAINER_M2_REPO, read_only=True),
            ],
            workdir=CONTAINER_WORKDIR,
            network_enabled=False,
        )
        rel = resolved.relative_to(self._project.root)
        if result.exit_code == 0:
            return f"쓰기 완료: {rel} — 컴파일 성공"
        tail = "\n".join(result.output.splitlines()[-COMPILE_TAIL_LINES:])
        return f"쓰기 완료: {rel} — 컴파일 실패:\n{tail}"
