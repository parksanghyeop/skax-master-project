"""품질 게이트 5종의 Java 구현 — 마지막 검문소 (M6, v4 2.4).

전부 LLM 없는 기계적 검사다(R2). 원리: "좋은 테스트인가"를 판단하지 않고
"측정 가능한 규칙을 어겼는가"만 본다. 정당해 보이는 위반도 일단 탈락시키고
사람 확인 목록으로 보낸다 — 잘못 탈락은 있어도 잘못 통과는 없게(보수적).
기준선(baseline)은 에이전트 실행 **전에** 떠 둔다.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from cta.adapters.java.coverage import JACOCO_XML_PATH, coverage_command
from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import extract_assert_statements
from cta.adapters.java.runner import CONTAINER_M2_REPO, CONTAINER_WORKDIR, MAVEN_IMAGE
from cta.core.gates import GateConfig, GateResult
from cta.sandbox.docker_sandbox import DockerSandbox, Mount

# 스킵 어노테이션 — 새로 붙으면 탈락(v4 2.4 ②). 코드에서 그대로 읽힌다.
# 패키지 전체 경로(@org.junit.jupiter.api.Disabled)로 우회하는 것도 잡는다.
_SKIP_ANNOTATION = re.compile(r"@\s*(?:[\w$]+\.)*(Disabled|Ignore)\b")


def _rel_java_files(project: MavenProject) -> dict[str, Path]:
    """소스 트리(main+test)의 .java 파일을 프로젝트 기준 상대 경로로 모은다."""
    result = {}
    for root in (project.root / "src" / "main" / "java", project.test_source_dir):
        if root.is_dir():
            for p in sorted(root.rglob("*.java")):
                result[p.relative_to(project.root).as_posix()] = p
    return result


@dataclass(frozen=True)
class SourceBaseline:
    """에이전트 실행 전의 소스 상태 — 게이트 ①②③의 비교 기준."""

    asserts: dict[str, tuple[str, ...]]  # 테스트 파일 → assert 호출문(정규화) 목록
    skip_counts: dict[str, int]  # 테스트 파일 → 스킵 어노테이션 수
    file_hashes: dict[str, str]  # 전체 소스(main+test) → sha256


def snapshot_baseline(project: MavenProject) -> SourceBaseline:
    """게이트 비교 기준선을 뜬다. 에이전트가 손대기 전에 호출해야 의미가 있다."""
    asserts: dict[str, tuple[str, ...]] = {}
    skip_counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    test_root = project.test_source_dir.resolve()
    for rel, path in _rel_java_files(project).items():
        text = path.read_text(encoding="utf-8", errors="replace")
        hashes[rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if path.resolve().is_relative_to(test_root):
            asserts[rel] = tuple(extract_assert_statements(text))
            skip_counts[rel] = len(_SKIP_ANNOTATION.findall(text))
    return SourceBaseline(asserts=asserts, skip_counts=skip_counts, file_hashes=hashes)


class AssertIntegrityGate:
    """게이트 ① assert 검사 — 기존 assert 호출문이 삭제·변경(완화 포함)되면 탈락.

    왜 내용 비교인가: 개수만 세면 assertEquals→assertNotNull 완화를 놓친다.
    왜 판단하지 않는가: 정당한 assert 변경인지 기계는 모른다 — 일단 탈락시키고
    사람 확인으로 보낸다(v4 2.4). 새 assert 추가는 자유다.
    """

    name = "assert"

    def __init__(self, project: MavenProject, baseline: SourceBaseline) -> None:
        self._project = project
        self._baseline = baseline

    def check(self) -> GateResult:
        damaged: list[str] = []
        for rel, old_asserts in self._baseline.asserts.items():
            path = self._project.root / rel
            if not path.is_file():
                damaged.append(f"{rel}: 테스트 파일이 삭제됨")
                continue
            new_asserts = extract_assert_statements(
                path.read_text(encoding="utf-8", errors="replace")
            )
            for stmt in set(old_asserts):
                if new_asserts.count(stmt) < old_asserts.count(stmt):
                    damaged.append(f"{rel}: 기존 assert 훼손 — {stmt[:120]}")
        if damaged:
            return GateResult(
                self.name,
                False,
                "기존 assert가 삭제·변경됐다(완화 의심). 사람 확인 필요:\n" + "\n".join(damaged),
            )
        total = sum(len(v) for v in self._baseline.asserts.values())
        return GateResult(self.name, True, f"기존 assert {total}개 모두 보존됨")


class SkipAnnotationGate:
    """게이트 ② 스킵 검사 — @Disabled/@Ignore가 새로 붙으면 탈락 (v4 2.4 ②)."""

    name = "skip"

    def __init__(self, project: MavenProject, baseline: SourceBaseline) -> None:
        self._project = project
        self._baseline = baseline

    def check(self) -> GateResult:
        offenders = []
        test_root = self._project.test_source_dir.resolve()
        for rel, path in _rel_java_files(self._project).items():
            if not path.resolve().is_relative_to(test_root):
                continue
            now = len(_SKIP_ANNOTATION.findall(path.read_text(encoding="utf-8", errors="replace")))
            before = self._baseline.skip_counts.get(rel, 0)
            if now > before:
                offenders.append(f"{rel}: 스킵 어노테이션 {before}→{now}개")
        if offenders:
            return GateResult(
                self.name, False, "테스트를 스킵 처리했다(금지):\n" + "\n".join(offenders)
            )
        return GateResult(self.name, True, "새 스킵 어노테이션 없음")


class FileScopeGate:
    """게이트 ③ 범위 검사 — 허용 목록 밖 파일이 바뀌면 탈락 (v4 2.4 ③).

    write_test 도구도 테스트 폴더를 강제하지만, 검문소는 도구를 신뢰하지 않고
    소스 전체(main 포함)의 해시를 다시 대조한다.
    """

    name = "scope"

    def __init__(self, project: MavenProject, baseline: SourceBaseline, allowed: set[str]) -> None:
        self._project = project
        self._baseline = baseline
        self._allowed = {Path(a).as_posix() for a in allowed}

    def check(self) -> GateResult:
        violations = []
        now_files = _rel_java_files(self._project)
        for rel, path in now_files.items():
            digest = hashlib.sha256(
                path.read_text(encoding="utf-8", errors="replace").encode("utf-8")
            ).hexdigest()
            before = self._baseline.file_hashes.get(rel)
            if before is None and rel not in self._allowed:
                violations.append(f"{rel}: 허용 목록 밖 새 파일")
            elif before is not None and before != digest and rel not in self._allowed:
                violations.append(f"{rel}: 허용 목록 밖 수정")
        for rel in self._baseline.file_hashes:
            if rel not in now_files and rel not in self._allowed:
                violations.append(f"{rel}: 허용 목록 밖 삭제")
        if violations:
            return GateResult(self.name, False, "계획에 없는 파일 변경:\n" + "\n".join(violations))
        return GateResult(self.name, True, f"변경이 허용 목록({len(self._allowed)}개) 안에 있음")


class CoverageGate:
    """게이트 ④ 커버리지 검사 — 대상 라인 80%/분기 70% 기준(설정 조정 가능, v4 2.4 ④).

    JaCoCo 실측으로 판정하고, 탈락 사유에 "어느 라인·분기가 실행되지 않았는지"를
    담는다 — 재시도 때 그 분기를 노린 테스트를 추가할 수 있게.
    """

    name = "coverage"

    def __init__(
        self,
        project: MavenProject,
        sandbox: DockerSandbox,
        m2_cache_dir,
        selector: str,
        target_source_file: str,  # 예: "Calculator.java"
        target_lines: set[int],  # 판정 대상 라인(변경 라인 또는 대상 메서드 범위)
        config: GateConfig,
    ) -> None:
        self._project = project
        self._sandbox = sandbox
        self._m2_cache_dir = m2_cache_dir
        self._selector = selector
        self._source_file = target_source_file
        self._target_lines = target_lines
        self._config = config

    def check(self) -> GateResult:
        result = self._sandbox.run(
            image=MAVEN_IMAGE,
            command=coverage_command(self._selector),
            mounts=[
                Mount(str(self._project.root), CONTAINER_WORKDIR),
                Mount(str(self._m2_cache_dir), CONTAINER_M2_REPO, read_only=True),
            ],
            workdir=CONTAINER_WORKDIR,
            network_enabled=False,
        )
        report = self._project.root / JACOCO_XML_PATH
        if result.exit_code != 0 or not report.is_file():
            # 측정 불가 = 통과 근거 없음 → 보수적으로 탈락(사람 확인)
            return GateResult(self.name, False, "커버리지 측정 실패 — 실행 로그 확인 필요")
        lines = parse_source_lines(report.read_text(encoding="utf-8"), self._source_file)
        relevant = {n: c for n, c in lines.items() if n in self._target_lines}
        if not relevant:
            return GateResult(
                self.name, False, f"대상 라인({self._source_file})이 리포트에 없음 — 측정 불가"
            )
        covered = [n for n, c in relevant.items() if c["ci"] > 0]
        uncovered = sorted(n for n, c in relevant.items() if c["ci"] == 0)
        line_pct = len(covered) / len(relevant)
        total_branches = sum(c["mb"] + c["cb"] for c in relevant.values())
        missed_branch_lines = sorted(n for n, c in relevant.items() if c["mb"] > 0)
        branch_pct = (
            sum(c["cb"] for c in relevant.values()) / total_branches if total_branches else 1.0
        )
        problems = []
        if line_pct < self._config.line_min:
            problems.append(
                f"라인 {line_pct:.0%} < 기준 {self._config.line_min:.0%} (미실행 라인: {uncovered})"
            )
        if branch_pct < self._config.branch_min:
            problems.append(
                f"분기 {branch_pct:.0%} < 기준 {self._config.branch_min:.0%} "
                f"(미실행 분기가 있는 라인: {missed_branch_lines})"
            )
        if problems:
            return GateResult(self.name, False, "; ".join(problems))
        return GateResult(
            self.name, True, f"라인 {line_pct:.0%}, 분기 {branch_pct:.0%} (기준 충족)"
        )


def parse_source_lines(jacoco_xml: str, source_file: str) -> dict[int, dict]:
    """jacoco.xml에서 특정 소스 파일의 라인별 커버리지(mi/ci/mb/cb)를 뽑는다."""
    import xml.etree.ElementTree as ET

    result: dict[int, dict] = {}
    root = ET.fromstring(jacoco_xml)
    for sf in root.iter("sourcefile"):
        if sf.get("name") != source_file:
            continue
        for line in sf.findall("line"):
            result[int(line.get("nr", "0"))] = {
                "mi": int(line.get("mi", "0")),
                "ci": int(line.get("ci", "0")),
                "mb": int(line.get("mb", "0")),
                "cb": int(line.get("cb", "0")),
            }
    return result
