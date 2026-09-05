"""MCP 도구 핸들러 — cli 서브커맨드를 Namespace로 호출하고 화면 출력을 돌려준다 (ADR-0018).

왜 cli 함수를 그대로 부르나: CLI와 MCP가 같은 core 조립 함수를 거쳐야 로직이 한 곳에 있다
(phase3 스킬 "CLI와 MCP에 로직 복제 금지"). 이 파일은 인자 변환 + 출력 캡처만 한다.
MCP SDK를 import하지 않으므로 SDK 없이도 단위 테스트가 된다. 층: mcp(cli 위).

stdout 캡처가 필수인 이유: MCP stdio 전송은 표준 출력을 프로토콜 채널로 쓴다. cli가 print한 화면이
그대로 새면 프로토콜이 깨진다 — 전부 문자열로 모아 도구 결과로 돌려준다.
"""

import argparse
import io
import threading
from collections.abc import Callable
from contextlib import redirect_stdout

from cta.cli.hints import render_error
from cta.cli.main import _cmd_apply, _cmd_diff, _cmd_generate
from cta.cli.maintain_cmd import run_maintain
from cta.cli.resolve_cmd import run_resolve

EXIT_LINE = "종료 코드"

# redirect_stdout은 프로세스 전역(sys.stdout)을 바꾼다. 서버가 도구 호출을 동시에 처리하면
# 두 호출의 화면이 섞이므로 한 번에 하나만 실행한다 — 샌드박스·게이트웨이 호출도 직렬이 안전하다.
_ONE_AT_A_TIME = threading.Lock()


def _run(func: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> str:
    """서브커맨드를 실행해 화면 출력 + 종료 코드 한 줄을 돌려준다. 예외도 안내 문구로 담는다."""
    buffer = io.StringIO()
    with _ONE_AT_A_TIME, redirect_stdout(buffer):
        try:
            code = func(args)
        except Exception as e:  # noqa: BLE001 — 도구 결과로 원인·다음 행동을 돌려준다(main()과 같은 정책)
            print(render_error(e))
            code = 1
    return f"{buffer.getvalue().rstrip()}\n\n{EXIT_LINE}: {code}"


def generate(project: str, target: str, max_methods: int = 4, fast: bool = False) -> str:
    """테스트 생성 — 클래스의 테스트 없는 메서드에 JUnit 테스트를 만들어 제안으로 보관한다.

    project: Maven 프로젝트 루트(pom.xml 위치). target: 클래스 이름(FQN 허용) 또는 "Class#m1,m2".
    max_methods: 한 번에 만들 메서드 수 상한. fast: Docker 없이 이 PC의 Maven으로 실행(격리 없음)
      + 커버리지·뮤테이션 게이트 생략(ADR-0019).
    반환: 화면 출력 전체 + "종료 코드: N" (0 정상 / 2 품질 미달 / 3 사람 확인 / 1 오류).
    수 분 걸릴 수 있다.
    """
    args = argparse.Namespace(
        file=None,
        class_name=None if "#" in target else target,
        target=target if "#" in target else None,
        project=project,
        test_class=None,
        instruction="",
        model=None,
        warmup_test=None,
        fast=fast,
        non_interactive=True,
        max_methods=max_methods,
        all=False,
        quiet=True,
    )
    return _run(_cmd_generate, args)


def maintain(project: str, diff: str = "HEAD", plan_only: bool = False, fast: bool = False) -> str:
    """변경 대응 — git 변경을 건별로 판단하고 규칙표대로 테스트를 추가하거나 사람 확인으로 멈춘다.

    diff: 비교 기준 커밋(기본 HEAD = 미커밋 변경, 예: "HEAD~1", "origin/main").
    plan_only: 판단만 출력하고 처리하지 않는다.
    반환: 화면 출력 + "종료 코드: N". 3이면 사람 확인 항목이 저장됐다 → resolve 도구로 답한다.
    """
    args = argparse.Namespace(
        project=project,
        diff=diff,
        plan_only=plan_only,
        fast=fast,
        non_interactive=True,
        quiet=True,
    )
    return _run(run_maintain, args)


def resolve(
    project: str,
    decision: str,
    escalation_id: str = "",
    hint: str = "",
    fast: bool = False,
) -> str:
    """판단 전달 — 멈춘 항목에 답해 저장된 지점부터 재개한다.

    decision: "intended"(일부러 동작을 바꿨다 → 기대값을 새 기준으로) / "test-issue"(테스트 문제 →
      실패 테스트를 동작 기준으로 재작성) / "proceed"(계획대로 생성) / "skip"(건너뜀, 기록만).
    escalation_id: 생략하면 항목이 1건일 때 자동 선택. hint: 에이전트에 전달할 지시.
    """
    choices = ("intended", "test-issue", "proceed", "skip")
    if decision not in choices:
        return f"decision은 {', '.join(choices)} 중 하나여야 한다: {decision!r}\n\n{EXIT_LINE}: 1"
    args = argparse.Namespace(
        project=project,
        id=escalation_id or None,
        intended=decision == "intended",
        test_issue=decision == "test-issue",
        proceed=decision == "proceed",
        skip=decision == "skip",
        hint=hint,
        fast=fast,
        non_interactive=True,
        quiet=True,
    )
    return _run(run_resolve, args)


def list_proposals(project: str, name: str = "") -> str:
    """변경 내용 확인 — 대기 중인 제안 목록, 또는 이름을 주면 그 제안의 코드 diff."""
    return _run(_cmd_diff, argparse.Namespace(project=project, name=name or None))


def apply(project: str, name: str = "", all: bool = False) -> str:  # noqa: A002 — CLI 플래그 이름과 같게
    """반영 — 제안을 테스트 트리에 쓴다. 소스에 손대는 유일한 도구다. 이름 생략 시 1건이면 자동."""
    return _run(_cmd_apply, argparse.Namespace(project=project, name=name or None, all=all))


TOOLS: tuple[Callable[..., str], ...] = (generate, maintain, resolve, list_proposals, apply)
