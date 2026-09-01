"""절대 규칙 R1(층 분리) 검사.

core/는 대상 언어를 모른다 — 언어·빌드 도구 이름 문자열과 바깥 층 import가
core/ 아래에 등장하면 실패한다. 이 테스트를 예외 처리로 우회하는 것 자체가
금지다(CLAUDE.md R1). 검사는 단순 문자열 스캔이라 결정적이다.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "cta" / "core"

# CLAUDE.md R1이 명시한 금지 문자열 목록 그대로. 대소문자 무시로 검사한다.
FORBIDDEN_WORDS = ("java", "maven", "pom.xml", "junit", "jacoco", "mvn", "pitest")

# 의존 방향 검사: core는 안쪽 층이라 바깥 층(adapters, llm)을 import할 수 없다.
# cta/ 이동 후에는 import 경로가 cta.adapters 형태라 두 표기 모두 검사한다.
FORBIDDEN_IMPORTS = (
    "import adapters",
    "from adapters",
    "import llm",
    "from llm",
    "import cta.adapters",
    "from cta.adapters",
    "import cta.llm",
    "from cta.llm",
)


def _core_files() -> list[Path]:
    files = sorted(CORE_DIR.rglob("*.py"))
    # 경로가 틀어져 빈 목록을 돌면 테스트가 통째로 헛돌므로 여기서 잡는다.
    assert files, f"core/에서 파이썬 파일을 찾지 못했다: {CORE_DIR}"
    return files


def test_core_has_no_language_specific_words():
    violations = []
    for path in _core_files():
        text = path.read_text(encoding="utf-8").lower()
        for word in FORBIDDEN_WORDS:
            if word in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {word!r}")
    assert not violations, "core/에 언어 종속 문자열 발견(R1 위반):\n" + "\n".join(violations)


def test_core_does_not_import_outer_layers():
    violations = []
    for path in _core_files():
        text = path.read_text(encoding="utf-8")
        for stmt in FORBIDDEN_IMPORTS:
            if stmt in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {stmt!r}")
    assert not violations, "core/가 바깥 층을 import한다(의존 방향 위반):\n" + "\n".join(violations)
