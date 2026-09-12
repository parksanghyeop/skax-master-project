"""기존 테스트 파일 + 모델이 출력한 "새 멤버 조각" → 파일 전체 (ADR-0023 결정 2).

왜 필요한가: 기존 테스트 클래스에 메서드를 추가할 때 모델이 파일 전체를 다시 출력하면
기존 테스트 20개가 시도마다 출력 토큰으로 나간다. 조각만 받고 여기서 합친다.
층: adapters/java — import 문·클래스 중괄호는 Java 지식이라 core에 두지 않는다(R1).
"""

import re

# 조각 안의 package 문은 버린다 — 기존 파일의 것이 진실이다
_PACKAGE_LINE = re.compile(r"^\s*package\s+[\w.]+\s*;\s*$")
_IMPORT_LINE = re.compile(r"^\s*import\s+(static\s+)?[\w.*]+\s*;\s*$")
# 모델이 규칙을 어기고 class 선언으로 감쌌을 때 안쪽만 취하기 위한 탐지
_CLASS_DECL = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+|final\s+|abstract\s+)*class\s+\w+", re.M
)

MEMBER_INDENT = "    "  # 클래스 본문 들여쓰기 — 프로젝트 관례(4칸)와 같다


def split_fragment(fragment: str) -> tuple[list[str], str]:
    """조각을 (import 문 목록, 멤버 본문)으로 나눈다. class 래핑이 있으면 벗긴다."""
    imports: list[str] = []
    body_lines: list[str] = []
    for line in fragment.splitlines():
        if _PACKAGE_LINE.match(line):
            continue
        if _IMPORT_LINE.match(line):
            imports.append(line.strip())
            continue
        body_lines.append(line)
    body = "\n".join(body_lines).strip("\n")
    body = _unwrap_class(body)
    return imports, body


def _unwrap_class(body: str) -> str:
    """`class X { … }`로 감싼 조각이면 중괄호 안쪽만 돌려준다. 아니면 그대로."""
    m = _CLASS_DECL.search(body)
    if not m:
        return body
    open_idx = body.find("{", m.end())
    close_idx = body.rfind("}")
    if open_idx < 0 or close_idx <= open_idx:
        return body
    return body[open_idx + 1 : close_idx].strip("\n")


def _indent_members(body: str) -> str:
    """멤버 본문을 클래스 안 들여쓰기(4칸)에 맞춘다 — 공통 들여쓰기를 벗기고 4칸을 다시 붙인다.

    함정(2026-09-13 실측): 모델 조각의 첫 줄(`@Test`)만 들여쓰기가 없고 나머지는 4칸이면,
    첫 줄만 보고 4칸을 더 얹어 본문이 8칸이 됐다. 그래서 첫 줄을 제외한 줄들의 최소 들여쓰기를
    기준으로 벗긴다(첫 줄은 왼쪽 공백을 전부 벗긴다). 빈 줄은 빈 줄로 둔다.
    """
    lines = body.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return body
    widths = [len(ln) - len(ln.lstrip()) for ln in non_empty[1:]] or [
        len(non_empty[0]) - len(non_empty[0].lstrip())
    ]
    base = min(widths)
    out = []
    first_seen = False
    for ln in lines:
        if not ln.strip():
            out.append("")
            continue
        width = len(ln) - len(ln.lstrip())
        stripped = ln.lstrip() if not first_seen else ln[min(width, base) :]
        first_seen = True
        out.append(MEMBER_INDENT + stripped)
    return "\n".join(out)


def merge_test_members(existing: str, fragment: str) -> str:
    """기존 테스트 파일에 조각의 import(중복 제외)와 멤버를 넣어 파일 전체를 만든다.

    입력: existing — 기존 파일 전체, fragment — 모델 출력(코드 블록 안쪽).
    출력: 파일 전체. 기존 내용은 한 글자도 바꾸지 않고, 멤버는 마지막 `}` 앞에 들어간다.
    실패 시 동작: 기존 파일에 `}`가 없으면(클래스가 아니면) ValueError — 조용히 이어붙이지 않는다.
    """
    imports, body = split_fragment(fragment)
    close_idx = existing.rfind("}")
    if close_idx < 0:
        raise ValueError("기존 테스트 파일에서 클래스 닫는 중괄호를 찾지 못했다")

    merged = existing
    new_imports = [imp for imp in imports if imp not in existing]
    if new_imports:
        merged = _insert_imports(merged, new_imports)
        close_idx = merged.rfind("}")

    if body.strip():
        head = merged[:close_idx].rstrip("\n")
        tail = merged[close_idx:]
        merged = f"{head}\n\n{_indent_members(body)}\n{tail}"
    return merged


def _insert_imports(existing: str, new_imports: list[str]) -> str:
    """마지막 import 뒤(없으면 package 문 뒤, 그것도 없으면 맨 앞)에 import를 넣는다."""
    lines = existing.splitlines(keepends=True)
    last_import = -1
    package_at = -1
    for i, line in enumerate(lines):
        if _IMPORT_LINE.match(line):
            last_import = i
        elif _PACKAGE_LINE.match(line):
            package_at = i
    block = "".join(imp + "\n" for imp in new_imports)
    if last_import >= 0:
        at = last_import + 1
    elif package_at >= 0:
        at = package_at + 1
        block = "\n" + block
    else:
        at = 0
    lines.insert(at, block)
    return "".join(lines)
