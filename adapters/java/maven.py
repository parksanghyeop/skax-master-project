"""Maven 프로젝트 탐지.

왜 필요한가: 어댑터의 모든 동작(준비·실행·테스트 쓰기)은 "여기가 Maven
프로젝트다"라는 확인에서 출발한다. 탐지 실패를 뒤늦게 mvn 오류로 만나지 않도록
입구에서 결정적으로 검사한다. 층: adapters/java.
"""

from dataclasses import dataclass
from pathlib import Path


class NotAMavenProjectError(ValueError):
    """pom.xml이 없는 경로를 Maven 프로젝트로 쓰려 할 때 던지는 예외."""


@dataclass(frozen=True)
class MavenProject:
    """탐지된 Maven 프로젝트의 위치 정보.

    root: 프로젝트 루트(pom.xml이 있는 디렉터리)의 절대 경로.
    """

    root: Path

    @property
    def pom_path(self) -> Path:
        return self.root / "pom.xml"

    @property
    def test_source_dir(self) -> Path:
        """테스트 소스 루트. Maven 표준 배치라 경로가 고정이다."""
        return self.root / "src" / "test" / "java"


def detect_maven_project(path: str | Path) -> MavenProject:
    """path가 Maven 프로젝트 루트인지 확인하고 MavenProject를 돌려준다.

    입력: 프로젝트 루트로 기대하는 경로.
    실패 시 동작: pom.xml이 없으면 NotAMavenProjectError — 무엇이 없었는지
      경로를 담아 알려준다.
    """
    root = Path(path).resolve()
    if not (root / "pom.xml").is_file():
        raise NotAMavenProjectError(f"pom.xml이 없다: {root}")
    return MavenProject(root=root)
