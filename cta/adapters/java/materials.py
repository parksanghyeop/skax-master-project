"""재료 수집 — 테스트를 쓰는 데 필요한 것을 한 번에 모은다 (시나리오 SC-001 1~2단계).

무엇을 모으나: ① 테스트 만들 메서드 선정 ② 확인해야 할 항목(분기·경계값·예외·null)
③ 파라미터·의존 객체 만드는 법(직접 생성 / builder / mock) ④ 기존 테스트 파일.
전부 정규식 기반의 결정적 열거다 — "확인 항목 14개 (분기 8, 경계값 3, 예외 2, null 1)"
같은 수치를 LLM이 지어내지 않게 일반 코드가 세고, 그 목록을 프롬프트 재료로 준다.
층: adapters/java (ADR-0015 D5·D6).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import (
    JavaMethod,
    extract_methods,
    find_class_file,
    method_line_spans,
    read_package,
)

# 확인 항목 종류 — 화면 출력 순서이기도 하다
KIND_BRANCH = "분기"
KIND_BOUNDARY = "경계값"
KIND_EXCEPTION = "예외"
KIND_NULL = "null"
KINDS = (KIND_BRANCH, KIND_BOUNDARY, KIND_EXCEPTION, KIND_NULL)

_BRANCH = re.compile(r"\b(if|else|case|while|for)\b|\?[^:]*:")
_BOUNDARY = re.compile(
    r">=|<=|compareTo\(|signum\(\)|isEmpty\(\)|isBlank\(\)|\b[<>]\s*0\b|==\s*0\b"
)
_THROW = re.compile(r"\bthrow\s+new\s+(\w+)")
_NULL = re.compile(r"\bnull\b")

# 표준 타입 — 프로젝트 안에서 찾지 않고 직접 만든다
_STANDARD_TYPES = {
    "int", "long", "double", "float", "boolean", "char", "byte", "short",
    "Integer", "Long", "Double", "Float", "Boolean", "Character", "String",
    "BigDecimal", "BigInteger", "List", "Set", "Map", "Optional", "LocalDate",
    "LocalDateTime", "Object",
}  # fmt: skip

_PARAM = re.compile(r"(?:final\s+)?(?P<type>[\w.]+(?:<[^>]*>)?(?:\[\])*)\s+(?P<name>\w+)")
_FIELD = re.compile(
    r"^\s*private\s+(?:final\s+)?(?P<type>[\w.]+(?:<[^>]*>)?)\s+(?P<name>\w+)\s*(?:=|;)",
    re.MULTILINE,
)
_CALL_LIKE = re.compile(r"\b(\w+)\s*\(")
_BUILDER = re.compile(r"static\s+\w+\s+builder\s*\(")
_TYPE_DECL = re.compile(r"\b(?P<kind>class|interface|enum|record)\s+(?P<name>\w+)")


@dataclass(frozen=True)
class CheckItem:
    """확인해야 할 항목 하나 — 종류, 소스 줄 번호, 설명."""

    kind: str
    line: int
    description: str


@dataclass(frozen=True)
class ConstructionHint:
    """객체 만드는 법 — 시나리오 [2/4]의 한 줄 ("Order → 직접 생성 (Order.builder() 사용)")."""

    type_name: str
    strategy: str  # "직접 생성" | "mock 사용"
    reason: str


@dataclass(frozen=True)
class MethodPlan:
    """선정된 메서드 하나와 그 확인 항목."""

    name: str
    text: str
    start_line: int
    end_line: int
    check_items: tuple[CheckItem, ...]


@dataclass
class Materials:
    """재료 묶음 — 프롬프트 재료(render)와 화면 출력(CLI)이 같은 객체를 본다."""

    class_name: str
    package: str
    class_file: Path
    methods: list[MethodPlan]
    skipped: list[tuple[str, str]]  # (메서드 이름, 건너뛴 이유)
    constructions: list[ConstructionHint]
    existing_test_code: str = ""
    style_examples: str = ""
    # 대상 메서드 줄 범위 합집합 — 커버리지 게이트 판정 라인
    target_lines: set = field(default_factory=set)

    @property
    def check_items(self) -> list[CheckItem]:
        return [item for m in self.methods for item in m.check_items]

    def count_by_kind(self) -> dict[str, int]:
        counts = {k: 0 for k in KINDS}
        for item in self.check_items:
            counts[item.kind] += 1
        return counts


def enumerate_check_items(method_text: str, start_line: int) -> tuple[CheckItem, ...]:
    """메서드 본문을 줄 단위로 훑어 확인 항목을 센다. 시그니처 줄은 제외."""
    items: list[CheckItem] = []
    lines = method_text.splitlines()
    for offset, raw in enumerate(lines[1:], start=1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("*") or line.startswith("/*"):
            continue
        no = start_line + offset
        for _ in _BRANCH.findall(line):
            items.append(CheckItem(KIND_BRANCH, no, line[:60]))
        if _BOUNDARY.search(line):
            items.append(CheckItem(KIND_BOUNDARY, no, line[:60]))
        for exc in _THROW.findall(line):
            items.append(CheckItem(KIND_EXCEPTION, no, f"{exc} 발생 조건"))
        if _NULL.search(line):
            items.append(CheckItem(KIND_NULL, no, line[:60]))
    return tuple(items)


def methods_referenced_in_tests(project: MavenProject) -> set[str]:
    """기존 테스트 소스가 호출 형태로 참조하는 식별자 집합.

    근사 판정인 이유: "그 메서드의 테스트가 있는가"의 정답은 커버리지 실측(그래프
    COVERS)이지만, 생성 명령은 그래프 없이도 돌아야 한다. 호출 모양 참조만으로도
    '전혀 다뤄지지 않은 메서드'를 고르는 데는 충분하다.
    """
    referenced: set[str] = set()
    if not project.test_source_dir.is_dir():
        return referenced
    for path in project.test_source_dir.rglob("*.java"):
        referenced.update(_CALL_LIKE.findall(path.read_text(encoding="utf-8", errors="replace")))
    return referenced


def _is_public(method: JavaMethod) -> bool:
    signature = method.text.split("{", 1)[0].split()
    return "private" not in signature and "protected" not in signature


def select_methods(
    project: MavenProject,
    class_file: Path,
    max_methods: int | None,
    only: list[str] | None = None,
    include_all: bool = False,
) -> tuple[list[MethodPlan], list[tuple[str, str]]]:
    """테스트 만들 메서드를 고른다.

    only가 있으면 그 이름들만(지정 실행). 아니면 공개 메서드 중 기존 테스트가 참조하지
    않는 것을 확인 항목 수가 많은 순(같으면 파일 순)으로 최대 max_methods개.
    출력: (선정 목록, [(건너뛴 이름, 이유)]).
    """
    source = class_file.read_text(encoding="utf-8", errors="replace")
    spans = {s.name: s for s in method_line_spans(source)}
    referenced = set() if include_all or only else methods_referenced_in_tests(project)
    candidates: list[MethodPlan] = []
    skipped: list[tuple[str, str]] = []
    for m in extract_methods(source):
        # 생성자는 파서가 "반환 타입 없는 메서드"로 잡는다 — 이름이 클래스와 같으면 생성자다
        if m.is_test or m.name == class_file.stem:
            continue
        if only is not None and m.name not in only:
            continue
        if only is None and not _is_public(m):
            skipped.append((m.name, "private 메서드 — 공개 동작을 통해 시험된다"))
            continue
        if only is None and m.name in referenced:
            skipped.append((m.name, "기존 테스트가 이미 참조 (강제 생성: --all)"))
            continue
        span = spans.get(m.name)
        start = span.start_line if span else 0
        end = span.end_line if span else 0
        candidates.append(
            MethodPlan(m.name, m.text, start, end, enumerate_check_items(m.text, start))
        )
    if only is not None:
        missing = [name for name in only if name not in {c.name for c in candidates}]
        for name in missing:
            skipped.append((name, "클래스에 그 이름의 메서드가 없다"))
        return candidates, skipped
    order = {c.name: i for i, c in enumerate(candidates)}
    ranked = sorted(candidates, key=lambda c: (-len(c.check_items), order[c.name]))
    if max_methods is not None and len(ranked) > max_methods:
        for extra in ranked[max_methods:]:
            skipped.append((extra.name, f"--max-methods {max_methods} 초과 — 다음 실행에서"))
        ranked = ranked[:max_methods]
    return sorted(ranked, key=lambda c: order[c.name]), skipped


def _strip_generics(type_name: str) -> str:
    return re.sub(r"<.*>", "", type_name).replace("[]", "").strip().rsplit(".", 1)[-1]


def parameter_types(method_text: str) -> list[str]:
    signature = method_text.split("{", 1)[0]
    inside = signature[signature.find("(") + 1 : signature.rfind(")")]
    if not inside.strip():
        return []
    # 제네릭 안의 쉼표(Map<String, Integer>)는 파라미터 구분자가 아니다
    parts, depth, buf = [], 0, ""
    for ch in inside:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    types = []
    for part in parts:
        m = _PARAM.search(part.strip())
        if m:
            types.append(_strip_generics(m.group("type")))
    return types


def describe_construction(project: MavenProject, type_name: str) -> ConstructionHint:
    """타입 하나를 테스트에서 어떻게 만들지 결정적으로 판단한다."""
    if type_name in _STANDARD_TYPES:
        return ConstructionHint(type_name, "직접 생성", "표준 타입")
    path = find_class_file(project, type_name)
    if path is None:
        return ConstructionHint(type_name, "직접 생성", "프로젝트 밖 타입 — 생성자 확인 필요")
    source = path.read_text(encoding="utf-8", errors="replace")
    decl = _TYPE_DECL.search(source)
    kind = decl.group("kind") if decl else "class"
    if kind == "interface":
        if "Repository" in type_name or "Repository<" in source:
            return ConstructionHint(type_name, "mock 사용", "DB에 접근하는 인터페이스")
        return ConstructionHint(type_name, "mock 사용", "인터페이스")
    if kind == "enum":
        return ConstructionHint(type_name, "직접 생성", "enum 상수")
    if kind == "record":
        return ConstructionHint(type_name, "직접 생성", "record — 생성자에 값 전달")
    if _BUILDER.search(source):
        return ConstructionHint(type_name, "직접 생성", f"{type_name}.builder() 사용")
    if "@Service" in source or "@Component" in source:
        return ConstructionHint(type_name, "직접 생성", "생성자에 의존성 주입")
    return ConstructionHint(type_name, "직접 생성", "값만 담는 객체")


def locate_test_file(project: MavenProject, package: str, test_class: str) -> Path:
    """테스트 클래스 파일의 경로를 정한다 — 이미 있으면 그 파일, 없으면 대상 패키지 아래 새 경로.

    왜 이름으로 먼저 찾나: maintain은 그래프가 찾아 준 검증 테스트 클래스(예: OrderServiceTest)에
    메서드를 추가하는데, 그 파일이 대상 클래스와 다른 패키지에 있을 수 있다. 패키지로만 경로를
    만들면 같은 이름의 새 파일이 다른 곳에 생겨 "기존 파일에 추가"가 조용히 실패한다.
    """
    if project.test_source_dir.is_dir():
        hits = sorted(project.test_source_dir.rglob(f"{test_class}.java"))
        if hits:
            return hits[0]
    return project.test_source_dir.joinpath(*package.split("."), f"{test_class}.java")


def collect_materials(
    project: MavenProject,
    class_file: Path,
    methods: list[MethodPlan],
    skipped: list[tuple[str, str]],
    test_class: str,
) -> Materials:
    """선정된 메서드들에 대한 재료 묶음을 만든다 (재료는 한 번에 모아 넘긴다 — SC-001 2단계)."""
    source = class_file.read_text(encoding="utf-8", errors="replace")
    package = read_package(source)
    # 파라미터 타입 + 대상 클래스의 필드 의존성(예: OrderRepository) — 순서 유지, 중복 제거
    types: list[str] = []
    for m in methods:
        for t in parameter_types(m.text):
            if t not in types:
                types.append(t)
    for fm in _FIELD.finditer(source):
        t = _strip_generics(fm.group("type"))
        if t not in types and t not in _STANDARD_TYPES:
            types.append(t)
    constructions = [describe_construction(project, t) for t in types if t != class_file.stem]

    test_path = locate_test_file(project, package, test_class)
    existing = (
        test_path.read_text(encoding="utf-8", errors="replace") if test_path.is_file() else ""
    )
    lines: set[int] = set()
    for m in methods:
        lines.update(range(m.start_line, m.end_line + 1))
    return Materials(
        class_name=class_file.stem,
        package=package,
        class_file=class_file,
        methods=methods,
        skipped=skipped,
        constructions=constructions,
        existing_test_code=existing,
        target_lines=lines,
    )


def render_materials(materials: Materials) -> str:
    """재료를 프롬프트에 붙일 문자열로 만든다 (writer 그래프의 extra_context)."""
    parts = ["[테스트를 만들 메서드]"]
    for m in materials.methods:
        parts.append(f"- {materials.class_name}#{m.name} ({m.start_line}~{m.end_line}행)")
    parts.append("\n[확인해야 할 항목 — 각 항목을 시험하는 테스트를 만들라]")
    for m in materials.methods:
        for item in m.check_items:
            parts.append(f"- {m.name} {item.line}행 [{item.kind}] {item.description}")
    parts.append("\n[파라미터·의존 객체 만드는 법]")
    for c in materials.constructions:
        parts.append(f"- {c.type_name} → {c.strategy} ({c.reason})")
    if materials.existing_test_code:
        parts.append(
            "\n[기존 테스트 파일 — 파일 전체를 출력하되 아래 기존 테스트 메서드와 assert는 "
            "한 글자도 바꾸지 말고 그대로 두고, 새 테스트 메서드만 추가하라]"
        )
        parts.append(materials.existing_test_code)
    return "\n".join(parts)


def check_item_satisfaction(items: list[CheckItem], line_coverage: dict[int, dict]) -> int:
    """확인 항목 중 몇 개가 실측으로 충족됐는지 센다 (시나리오 [4/4] "확인 항목 충족 11/14").

    판정(근사): 항목이 있는 줄이 실행됐고(ci>0), 분기 항목이면 그 줄의 분기가 전부
    실행됐을 때(mb==0) 충족. 커버리지 리포트는 "실행했다"이지 "검증했다"가 아니므로
    검출력(뮤테이션)과 함께 봐야 한다(v4 2.4).
    """
    satisfied = 0
    for item in items:
        cov = line_coverage.get(item.line)
        if not cov or cov.get("ci", 0) == 0:
            continue
        if item.kind == KIND_BRANCH and cov.get("mb", 0) > 0:
            continue
        satisfied += 1
    return satisfied
