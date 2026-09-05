"""오류 안내 — 실패 지점마다 "왜 / 할 일 / 명령" 세 줄을 낸다 (3단계 A-5, phase3 스킬 UX 항목).

판단 로직은 없다 — 예외 종류·문구를 표 하나에서 찾아 글자로 바꿀 뿐이다. 층: cli.
문구를 예외가 나는 자리마다 흩뿌리지 않고 여기 한 곳에 둔다 — 설치 직후 실패가 가장 많이
나는 곳(Docker 미실행, .env 없음, pom.xml 없음, 시간 초과, 기록 없음)이 전부 이 표에 있다.
출력 직전에 시크릿을 가린다(llm/masking) — 오류 문구에 키가 섞여도 화면에는 안 나온다.
"""

from collections.abc import Callable
from dataclasses import dataclass

from cta.adapters.java.maven import NotAMavenProjectError
from cta.llm.gateway import GatewayCallError, GatewayConfigError
from cta.llm.masking import mask_secrets
from cta.llm.metering import BudgetExceededError
from cta.llm.replay import CassetteError


@dataclass(frozen=True)
class Hint:
    """안내 세 줄. command는 없을 수 있다(확인만 하면 되는 경우)."""

    why: str
    todo: str
    command: str = ""


# Docker가 안 떠 있을 때 docker CLI·데몬이 내는 문구들 — 샌드박스 출력에 그대로 섞여 올라온다
_DOCKER_MARKERS = (
    "docker api",
    "docker daemon",
    "error during connect",
    "docker: not found",
    "cannot connect to the docker",
)


def _is_docker_problem(error: BaseException | None, text: str) -> bool:
    lowered = text.lower()
    if isinstance(error, FileNotFoundError) and "docker" in lowered:
        return True
    return any(marker in lowered for marker in _DOCKER_MARKERS)


# (조건, 안내) 표. 위에서부터 첫 일치가 이긴다 — 구체적인 것을 앞에 둔다.
_RULES: list[tuple[Callable[[BaseException | None, str], bool], Hint]] = [
    (
        lambda e, t: isinstance(e, GatewayConfigError) or "CTA_GATEWAY_API_KEY가 필요하다" in t,
        Hint(
            why="게이트웨이 주소·API 키가 설정에 없다",
            todo=".env를 실행 폴더 또는 ~/.cta/.env에 만들고 CTA_GATEWAY_URL, "
            "CTA_GATEWAY_API_KEY를 채운다 (.env는 커밋 금지)",
            command="copy .env.example .env   (그다음 값 채우기)",
        ),
    ),
    (
        lambda e, t: isinstance(e, GatewayCallError) and "대기 초과" in t,
        Hint(
            why="모델 응답이 시간 상한을 넘었다 — 메서드가 많으면 파일이 커져 100초를 넘기기도 함",
            todo="상한을 늘리거나 한 번에 만드는 메서드 수를 줄인다",
            command="cta.toml → [gateway] timeout_sec = 600   또는   --max-methods 2",
        ),
    ),
    (
        lambda e, t: isinstance(e, GatewayCallError),
        Hint(
            why="게이트웨이에 닿지 못했거나 요청이 거부됐다",
            todo="사내망(VPN) 연결, CTA_GATEWAY_URL 주소, API 키 유효기간을 확인한다",
        ),
    ),
    (
        lambda e, t: isinstance(e, CassetteError),
        Hint(
            why="재생 모드인데 저장된 LLM 호출 기록이 없거나 지금 요청과 다르다 — "
            "실호출로 몰래 넘어가지 않는다(R7)",
            todo="예제나 프롬프트를 바꿨다면 기록을 다시 만든다",
            command="python scripts/record_golden.py --live",
        ),
    ),
    (
        lambda e, t: isinstance(e, BudgetExceededError),
        Hint(
            why="이번 실행의 토큰 예산을 다 썼다. 생성 중이던 파일은 되돌려졌다",
            todo="예산을 늘리거나 한 번에 만드는 메서드 수를 줄인다",
            command="cta.toml → [budget] max_tokens_per_run   또는   --max-methods 2",
        ),
    ),
    (
        lambda e, t: isinstance(e, NotAMavenProjectError) or "pom.xml이 없다" in t,
        Hint(
            why="pom.xml이 없는 폴더다 — 단일 모듈 Maven 프로젝트만 지원한다",
            todo="프로젝트 루트를 지정한다",
            command="cta <명령> --project <pom.xml이 있는 폴더>",
        ),
    ),
    (
        _is_docker_problem,
        Hint(
            why="Docker가 실행 중이 아니거나 설치돼 있지 않다 — 테스트는 샌드박스에서만 돈다(R6)",
            todo="Docker Desktop을 실행하고 다시 시도한다",
            command="docker info",
        ),
    ),
    (
        lambda e, t: isinstance(e, KeyboardInterrupt),
        Hint(
            why="사용자가 중단했다",
            todo="생성 중이던 파일은 되돌려졌다. 다시 실행하면 의존성 캐시 덕에 빨리 시작한다",
        ),
    ),
    (
        lambda e, t: isinstance(e, ValueError) and "cta.toml" in t,
        Hint(
            why="설정 파일 값이 잘못됐다",
            todo="cta.toml의 해당 절을 고친다 (사용가이드 §9)",
        ),
    ),
]


def find_hint(error: BaseException | str) -> Hint | None:
    """예외 또는 오류 문구에 맞는 안내를 찾는다. 없으면 None."""
    exc = error if isinstance(error, BaseException) else None
    text = str(error)
    for matches, hint in _RULES:
        if matches(exc, text):
            return hint
    return None


def render_error(error: BaseException | str) -> str:
    """ "오류: 원인" + 안내 세 줄. 안내가 없는 예외는 CTA_DEBUG 안내를 붙인다.

    입력: 예외(진입점의 except) 또는 이미 문구로 만들어진 오류(run_generation의 report).
    출력: 화면에 그대로 찍을 여러 줄 문자열. 시크릿은 가려진다.
    """
    text = mask_secrets(str(error)).strip() or type(error).__name__
    lines = [f"오류: {text}"]
    hint = find_hint(error)
    if hint is not None:
        lines.append(f"  왜:    {hint.why}")
        lines.append(f"  할 일: {hint.todo}")
        if hint.command:
            lines.append(f"  명령:  {hint.command}")
    elif isinstance(error, BaseException):
        lines.append("  자세히: CTA_DEBUG=1 로 다시 실행하면 전체 오류 추적을 출력한다")
    return "\n".join(lines)
