"""PIT 뮤테이션 테스트 — 게이트 ⑤ "심은 버그를 잡는가" (M6, v4 2.4 ⑤).

정해진 변형 규칙(조건 뒤집기, 상수 바꾸기 등)으로 대상 코드에 작은 버그를
기계적으로 심고 테스트를 돌린다. 하나도 못 잡으면 "통과만 하는 빈 테스트"다.
대상 pom.xml을 고치지 않기 위해 PIT 플러그인을 끼운 복제 pom(overlay)을 만들어
쓴다. 층: adapters/java.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.runner import CONTAINER_M2_REPO, CONTAINER_WORKDIR, MAVEN_IMAGE
from cta.core.gates import GateResult
from cta.sandbox.docker_sandbox import DockerSandbox, Mount

# PIT 버전 쌍 — junit5 플러그인과의 호환 조합. 바꾸면 캐시 재준비 필요.
PIT_PLUGIN = "org.pitest:pitest-maven:1.15.8"
PIT_JUNIT5_VERSION = "1.2.1"

OVERLAY_POM_NAME = "pom-cta-pit.xml"  # 대상 프로젝트 루트에 생성(임시, gitignore 권장)
MUTATIONS_XML = "target/pit-reports/mutations.xml"

_PLUGIN_XML = f"""\
      <plugin>
        <groupId>org.pitest</groupId>
        <artifactId>pitest-maven</artifactId>
        <version>{PIT_PLUGIN.rsplit(":", 1)[1]}</version>
        <dependencies>
          <dependency>
            <groupId>org.pitest</groupId>
            <artifactId>pitest-junit5-plugin</artifactId>
            <version>{PIT_JUNIT5_VERSION}</version>
          </dependency>
        </dependencies>
      </plugin>
"""


def write_overlay_pom(project: MavenProject) -> Path:
    """PIT 플러그인을 끼운 복제 pom을 만든다. 원본 pom.xml은 건드리지 않는다.

    실패 시 동작: pom에 </plugins>가 없으면 RuntimeError — 문자열 삽입 방식의
    한계를 숨기지 않는다(빌드 구조가 다른 프로젝트는 pom에 직접 추가 안내).
    """
    source = project.pom_path.read_text(encoding="utf-8")
    if "</plugins>" not in source:
        raise RuntimeError("pom.xml에 <plugins> 절이 없어 PIT overlay를 만들 수 없다")
    overlay = project.root / OVERLAY_POM_NAME
    overlay.write_text(
        source.replace("</plugins>", _PLUGIN_XML + "      </plugins>", 1), encoding="utf-8"
    )
    return overlay


def mutation_command(target_class_fqcn: str, target_test_fqcn: str) -> list[str]:
    """지정 클래스·테스트만 뮤테이션 실행하는 mvn 명령(오프라인, overlay pom)."""
    return [
        "mvn",
        "-B",
        "-o",
        f"-Dmaven.repo.local={CONTAINER_M2_REPO}",
        "-f",
        OVERLAY_POM_NAME,
        "test-compile",
        f"{PIT_PLUGIN}:mutationCoverage",
        f"-DtargetClasses={target_class_fqcn}",
        f"-DtargetTests={target_test_fqcn}",
        "-DoutputFormats=XML",
        "-DtimestampedReports=false",
    ]


def parse_mutations(
    mutations_xml: str, methods: set[str] | None = None
) -> tuple[int, int, list[str]]:
    """mutations.xml에서 (죽인 수, 전체 수, 살아남은 변형 설명)을 뽑는다.

    methods를 주면 그 메서드들에 심긴 변형만 집계한다 — PIT는 클래스 단위로
    심는데, 판정 대상은 "생성 테스트가 노린 메서드"이기 때문이다. 다른 메서드의
    미커버 변형이 판정을 오염시키면 정당한 테스트가 억울하게 탈락한다.
    """
    root = ET.fromstring(mutations_xml)
    killed = 0
    total = 0
    survived: list[str] = []
    for m in root.iter("mutation"):
        if methods and m.findtext("mutatedMethod", default="") not in methods:
            continue
        total += 1
        status = m.get("status", "")
        if status == "KILLED":
            killed += 1
        elif status in ("SURVIVED", "NO_COVERAGE"):
            desc = m.findtext("description", default="?")
            line = m.findtext("lineNumber", default="?")
            survived.append(f"{line}행: {desc}")
    return killed, total, survived


def measure_mutation(
    project: MavenProject,
    sandbox: DockerSandbox,
    m2_cache_dir: str | Path,
    target_class_fqcn: str,
    target_test_fqcn: str,
    methods: set[str] | None = None,
) -> tuple[int, int, list[str]] | None:
    """PIT를 한 번 돌려 (죽인 수, 전체 수, 살아남은 변형)을 돌려준다. 측정 불가면 None.

    게이트 ⑤와 "버그 검출력 61% → 68%"(SC-002 전후 비교)가 같은 측정을 공유한다.
    """
    try:
        write_overlay_pom(project)
    except RuntimeError:
        return None
    sandbox.run(
        image=MAVEN_IMAGE,
        command=mutation_command(target_class_fqcn, target_test_fqcn),
        mounts=[
            Mount(str(project.root), CONTAINER_WORKDIR),
            Mount(str(m2_cache_dir), CONTAINER_M2_REPO, read_only=True),
        ],
        workdir=CONTAINER_WORKDIR,
        network_enabled=False,
    )
    report = project.root / MUTATIONS_XML
    if not report.is_file():
        return None
    return parse_mutations(report.read_text(encoding="utf-8"), methods)


class MutationGate:
    """게이트 ⑤ — 심은 버그를 하나도 못 잡거나 검출률이 기준 미만이면 탈락."""

    name = "mutation"

    def __init__(
        self,
        project: MavenProject,
        sandbox: DockerSandbox,
        m2_cache_dir,
        target_class_fqcn: str,
        target_test_fqcn: str,
        min_killed_ratio: float,
        target_methods: set[str] | None = None,  # 지정 시 그 메서드들의 변형만 판정
    ) -> None:
        self._project = project
        self._sandbox = sandbox
        self._m2_cache_dir = m2_cache_dir
        self._class_fqcn = target_class_fqcn
        self._test_fqcn = target_test_fqcn
        self._min_ratio = min_killed_ratio
        self._target_methods = target_methods
        # 마지막 측정값 — CLI가 "버그 검출력 n%"를 보여줄 때 재사용
        self.last_score: tuple[int, int] | None = None

    def check(self) -> GateResult:
        measured = measure_mutation(
            self._project,
            self._sandbox,
            self._m2_cache_dir,
            self._class_fqcn,
            self._test_fqcn,
            self._target_methods,
        )
        if measured is None:
            return GateResult(
                self.name, False, "뮤테이션 리포트 없음 — 측정 불가는 통과 근거가 아니다"
            )
        killed, total, survived = measured
        self.last_score = (killed, total)
        if total == 0:
            return GateResult(self.name, False, "심을 변형이 없음 — 대상 지정 확인 필요")
        ratio = killed / total
        if killed == 0 or ratio < self._min_ratio:
            sample = "; ".join(survived[:5])
            return GateResult(
                self.name,
                False,
                f"심은 버그 {total}개 중 {killed}개만 검출({ratio:.0%} < 기준 "
                f"{self._min_ratio:.0%}). 살아남은 변형 예: {sample}",
            )
        return GateResult(self.name, True, f"심은 버그 {total}개 중 {killed}개 검출({ratio:.0%})")
