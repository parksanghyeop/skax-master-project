"""도구 4/6 run_tests — 지정한 테스트만 샌드박스에서 실행 (v4 3절 "테스트 실행")."""

from core.ports import EmptySelectorError, TestRunner
from core.textlimit import clip


def run_tests(runner: TestRunner, selector: str, seed: int | None = None) -> str:
    """selector의 테스트를 실행하고 통과/실패와 내용을 문자열로 돌려준다.

    seed: 무작위 입력 테스트 재현용(v4 3절). PoC에서는 받기만 하고 전달하지
      않는다 — 어댑터 연결은 2단계. 도구 시그니처를 미리 맞춰 두는 이유는
      프롬프트·카세트가 시그니처 변경에 취약하기 때문이다.
    """
    try:
        result = runner.run(selector)
    except EmptySelectorError as e:
        # 모델에게는 예외가 아니라 문장으로 알린다 — 다음 행동(selector 지정)을 유도
        return clip(f"실행 거부: {e}")
    status = "통과" if result.passed else "실패"
    note = "" if seed is None else f"\n(참고: seed {seed}는 PoC에서 아직 반영되지 않는다)"
    return clip(f"{status}\n{result.summary}{note}")
