"""도구 3/6 write_test — 테스트 파일을 만들거나 고친다 (v4 3절 "테스트 쓰기")."""

from core.ports import TestWriter
from core.textlimit import clip


def write_test(writer: TestWriter, path: str, code: str) -> str:
    """파일을 쓰고 컴파일·정적 검사 결과를 돌려준다. 범위 위반은 어댑터가 거부한다."""
    return clip(writer.write(path, code))
