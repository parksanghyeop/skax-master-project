"""JaCoCo 커버리지 수집·파싱 — COVERS 엣지(검증한다)의 실측 근거 (M4/M6).

"이 테스트가 이 메서드를 실행한다"는 추측이 아니라 커버리지 기록에서 뽑는다
(v4 4.1). 테스트 클래스 단위로 격리 실행해 그 클래스가 실행한 메서드를 얻는다 —
메서드 단위 실행별 기록은 비용이 커서 클래스 단위 정밀도로 시작한다(알려진 한계).
층: adapters/java. M6 커버리지 게이트가 같은 파서를 재사용한다.
"""

import xml.etree.ElementTree as ET

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.runner import CONTAINER_M2_REPO, CONTAINER_WORKDIR, MAVEN_IMAGE
from cta.graph.model import EDGE_COVERS, GraphEdge
from cta.sandbox.docker_sandbox import DockerSandbox, Mount

# JaCoCo 플러그인 좌표. 준비 단계(runner.prepare)가 이 버전을 캐시에 채운다 —
# 버전을 바꾸면 기존 캐시로는 오프라인 실행이 실패하므로 재준비가 필요하다.
JACOCO_PLUGIN = "org.jacoco:jacoco-maven-plugin:0.8.12"

# mvn 실행 후 리포트가 생기는 표준 경로 (프로젝트 루트 기준)
JACOCO_XML_PATH = "target/site/jacoco/jacoco.xml"


def coverage_command(test_selector: str) -> list[str]:
    """지정한 테스트만 커버리지 계측과 함께 실행하는 mvn 명령(오프라인)."""
    return [
        "mvn",
        "-B",
        "-o",
        f"-Dmaven.repo.local={CONTAINER_M2_REPO}",
        # 함정: JaCoCo 실행 기록(jacoco.exec)은 기본적으로 이전 실행분에 덧붙여진다(append=true).
        # 그대로 두면 앞선 게이트·그래프 실측의 기록이 섞여 "이 테스트가 이 메서드를 실행했다"가
        # 틀리고 커버리지 수치가 부풀려진다 — 실측 발견(2026-09-03, hardening-notes). 매번 새로 쓴다
        "-Djacoco.append=false",
        # 테스트가 실패해도 리포트는 만든다 — "이 테스트가 이 메서드를 실행했는가"(COVERS)는
        # 통과 여부와 무관하고, 리팩터링으로 깨진 상태에서도 검증 테스트를 찾아야 한다(SC-003).
        # 통과 판정은 run_tests(러너)가 따로 한다.
        "-Dmaven.test.failure.ignore=true",
        f"{JACOCO_PLUGIN}:prepare-agent",
        "test",
        f"-Dtest={test_selector}",
        f"{JACOCO_PLUGIN}:report",
    ]


def parse_covered_methods(jacoco_xml: str) -> set[str]:
    """jacoco.xml에서 실제 실행된(라인 커버 > 0) 메서드 key 집합을 뽑는다.

    key 규칙은 그래프와 동일: "클래스이름#메서드이름" (패키지 생략, 그래프 모델의
    알려진 한계와 같은 수준). 생성자(<init>)·클래스 초기화(<clinit>)는 제외한다.
    """
    covered: set[str] = set()
    root = ET.fromstring(jacoco_xml)
    for cls in root.iter("class"):
        class_name = cls.get("name", "").split("/")[-1]
        for method in cls.findall("method"):
            name = method.get("name", "")
            if name in ("<init>", "<clinit>"):
                continue
            for counter in method.findall("counter"):
                if counter.get("type") == "LINE" and int(counter.get("covered", "0")) > 0:
                    covered.add(f"{class_name}#{name}")
                    break
    return covered


class JacocoCoverageCollector:
    """테스트 클래스별로 커버리지를 실측해 COVERS 엣지를 만든다."""

    def __init__(self, project: MavenProject, sandbox: DockerSandbox, m2_cache_dir) -> None:
        self._project = project
        self._sandbox = sandbox
        self._m2_cache_dir = m2_cache_dir

    def measure(self, test_class: str) -> set[str]:
        """test_class 하나를 계측 실행하고, 그 실행이 커버한 메서드 key를 돌려준다.

        실패 시 동작: 테스트 실패·리포트 없음 → 빈 집합 (그래프는 보조 정보라
        비어 있는 것이 틀린 엣지보다 낫다).
        """
        result = self._sandbox.run(
            image=MAVEN_IMAGE,
            command=coverage_command(test_class),
            mounts=[
                Mount(str(self._project.root), CONTAINER_WORKDIR),
                Mount(str(self._m2_cache_dir), CONTAINER_M2_REPO, read_only=True),
            ],
            workdir=CONTAINER_WORKDIR,
            network_enabled=False,
        )
        report = self._project.root / JACOCO_XML_PATH
        if result.exit_code != 0 or not report.is_file():
            return set()
        return parse_covered_methods(report.read_text(encoding="utf-8"))

    def collect_edges(self, test_classes: list[str]) -> list[GraphEdge]:
        """테스트 클래스 목록 전체를 실측해 COVERS(테스트 클래스 → 메서드) 엣지로."""
        edges = []
        for tc in test_classes:
            for method_key in sorted(self.measure(tc)):
                edges.append(GraphEdge(kind=EDGE_COVERS, src=tc, dst=method_key))
        return edges
