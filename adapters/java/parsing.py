"""Java 소스의 최소 파싱 — 메서드 추출과 모양(파라미터 수·예외 유무) 계산.

왜 정규식+중괄호 대응 수준인가: PoC의 "비슷한 모양의 테스트 찾기"(v4 4.1 쿼리)와
대상 조사에는 시그니처와 본문 텍스트면 충분하다. 제네릭·중첩 클래스까지 정확한
구문 트리(AST)가 필요해지는 2단계에서 전용 파서 도입을 검토한다(poc-findings 기록).
층: adapters/java.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from adapters.java.maven import MavenProject

# 메서드 시그니처: 수식어들 + 반환 타입 + 이름( 파라미터 ) [throws ...] {
# 생성자·제어문 오탐을 줄이기 위해 반환 타입 한 단어를 요구한다.
# 함정: 선두 lookbehind가 없으면 "@Test"의 Test까지 반환 타입으로 삼켜
# 어노테이션 인식(is_test)이 어긋난다 — 단어·@ 중간에서 시작하지 못하게 막는다.
_METHOD_SIGNATURE = re.compile(
    r"(?<![@\w])"
    r"(?:(?:public|protected|private|static|final|synchronized)\s+)*"
    r"[\w<>\[\],\s]+?\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*"
    r"(?:throws\s+[\w.,\s]+)?\s*\{"
)

# @Test 어노테이션이 시그니처 앞 이만큼 안에 있으면 테스트 메서드로 본다.
_TEST_ANNOTATION_WINDOW = 80

# 함정: 정규식의 반환 타입 부분이 공백만으로도 매칭돼 `if (x == 0) {` 같은
# 제어문이 이름 "if"인 메서드로 오인된다. Java에서 키워드는 메서드 이름이 될 수
# 없으므로 이름이 키워드면 무조건 오탐이다 — 파일 단위 전체 열거에서 실제로 발견됨.
_JAVA_KEYWORDS = frozenset(
    "if else for while do switch case catch try finally return throw new synchronized".split()
)


@dataclass(frozen=True)
class JavaMethod:
    """추출된 메서드 하나. shape 비교(파라미터 수·예외 유무)의 단위."""

    name: str
    param_count: int
    uses_exception: bool  # throws 선언 또는 본문의 throw — "예외 유무" 모양 신호
    text: str  # 시그니처부터 닫는 중괄호까지
    is_test: bool


def _match_brace_span(source: str, open_brace_index: int) -> int:
    """open_brace_index의 '{'와 짝이 되는 '}'의 인덱스를 돌려준다. 못 찾으면 -1."""
    depth = 0
    for i in range(open_brace_index, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_methods(source: str) -> list[JavaMethod]:
    """소스 텍스트에서 메서드들을 뽑는다. 파싱 실패한 부분은 조용히 건너뛴다."""
    methods = []
    for m in _METHOD_SIGNATURE.finditer(source):
        if m.group("name") in _JAVA_KEYWORDS:
            continue
        open_index = m.end() - 1
        close_index = _match_brace_span(source, open_index)
        if close_index < 0:
            continue
        body = source[m.start() : close_index + 1]
        params = m.group("params").strip()
        preceding = source[max(0, m.start() - _TEST_ANNOTATION_WINDOW) : m.start()]
        methods.append(
            JavaMethod(
                name=m.group("name"),
                param_count=0 if not params else params.count(",") + 1,
                uses_exception="throws" in m.group(0) or "throw " in body,
                text=body,
                is_test="@Test" in preceding,
            )
        )
    return methods


@dataclass(frozen=True)
class MethodSpan:
    """메서드의 소스 내 줄 범위(1부터, 양끝 포함) — diff 줄 번호를 메서드로 매핑할 때 쓴다."""

    name: str
    start_line: int
    end_line: int


def method_line_spans(source: str) -> list[MethodSpan]:
    """소스의 각 메서드가 차지하는 줄 범위를 돌려준다 (extract_methods와 같은 파싱)."""
    spans = []
    for m in _METHOD_SIGNATURE.finditer(source):
        close_index = _match_brace_span(source, m.end() - 1)
        if close_index < 0:
            continue
        spans.append(
            MethodSpan(
                name=m.group("name"),
                start_line=source.count("\n", 0, m.start()) + 1,
                end_line=source.count("\n", 0, close_index) + 1,
            )
        )
    return spans


def find_class_file(project: MavenProject, class_name: str) -> Path | None:
    """프로젝트에서 클래스 소스 파일을 찾는다 (main 우선, 없으면 test)."""
    for base in (project.root / "src" / "main" / "java", project.test_source_dir):
        if not base.is_dir():
            continue
        hits = sorted(base.rglob(f"{class_name}.java"))
        if hits:
            return hits[0]
    return None


_PACKAGE_DECL = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

_ASSERT_CALL_START = re.compile(r"\bassert\w*\s*\(")


def extract_assert_statements(source: str) -> list[str]:
    """assert 계열 호출문 전체(닫는 괄호까지)를 공백 정규화해 뽑는다.

    왜 필요한가: 게이트의 assert 훼손 검사는 "개수"가 아니라 "내용"을 비교해야
    assertEquals→assertNotNull 같은 완화를 잡는다(v4 2.4). 괄호 짝을 세므로
    인자 안의 중첩 호출·람다도 통째로 잡힌다.
    """
    statements = []
    for m in _ASSERT_CALL_START.finditer(source):
        open_index = m.end() - 1
        depth = 0
        for i in range(open_index, len(source)):
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
                if depth == 0:
                    raw = source[m.start() : i + 1]
                    statements.append(" ".join(raw.split()))
                    break
    return statements


def read_package(source: str) -> str:
    """소스의 package 선언을 읽는다. 없으면 빈 문자열(기본 패키지).

    왜 필요한가: 생성할 테스트 파일의 저장 경로는 대상 클래스의 패키지를
    따라가야 컴파일된다 — CLI가 경로를 자동 계산할 때 쓴다.
    """
    m = _PACKAGE_DECL.search(source)
    return m.group(1) if m else ""


def parse_target(target: str) -> tuple[str, str]:
    """ "Class#method" 식별자를 (클래스, 메서드)로 나눈다. 메서드가 없으면 빈 문자열."""
    class_name, _, method_name = target.partition("#")
    return class_name.strip(), method_name.strip()
