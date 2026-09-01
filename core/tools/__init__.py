"""도구 6개 — 테스트 작성 에이전트에게 주는 능력의 전부 (절대 규칙 R4).

1도구 1파일. 모든 도구는 예외 대신 모델이 읽을 문자열을 길이 상한(clip) 안에서
돌려준다(v4 3절). 7번째 도구가 필요해 보이면 만들지 말고 사용자에게 먼저 묻는다.
층: core — 도구는 포트만 알고, 어떤 언어를 다루는지 모른다(R1).
"""

from core.tools.check_quality import check_quality
from core.tools.inspect_target import inspect_target
from core.tools.query_code_graph import query_code_graph
from core.tools.report_finding import report_finding
from core.tools.run_tests import run_tests
from core.tools.write_test import write_test

__all__ = [
    "check_quality",
    "inspect_target",
    "query_code_graph",
    "report_finding",
    "run_tests",
    "write_test",
]
