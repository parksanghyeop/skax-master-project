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


def find_class_file(project: MavenProject, class_name: str) -> Path | None:
    """프로젝트에서 클래스 소스 파일을 찾는다 (main 우선, 없으면 test)."""
    for base in (project.root / "src" / "main" / "java", project.test_source_dir):
        if not base.is_dir():
            continue
        hits = sorted(base.rglob(f"{class_name}.java"))
        if hits:
            return hits[0]
    return None


def parse_target(target: str) -> tuple[str, str]:
    """ "Class#method" 식별자를 (클래스, 메서드)로 나눈다. 메서드가 없으면 빈 문자열."""
    class_name, _, method_name = target.partition("#")
    return class_name.strip(), method_name.strip()
