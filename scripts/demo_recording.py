"""시연 영상 녹화용 — examples/demo에 장면별 코드 변경을 넣어 주는 스크립트 (최종산출물/시연영상_시나리오.md와 한 쌍).

발표자는 코드를 손으로 고치지 않고, 장면마다 이 스크립트 한 줄 + cta 명령만 친다.
main은 건드리지 않는다 — 녹화용 브랜치(demo-recording)를 만들고 그 위에서만 커밋한다.

  python scripts/demo_recording.py prepare   # 브랜치 생성, examples/demo 초기화, Maven 예열
  python scripts/demo_recording.py scene2    # findById에 null 방어 추가 + 커밋  → cta maintain --diff HEAD~1 --impact
  python scripts/demo_recording.py scene3    # PricingCalculator 리팩터링(스케일 변경, 미커밋) → cta maintain --message … → resolve
  python scripts/demo_recording.py scene4    # 장면 3 결과 커밋 + total() 스트림 리팩터링(미커밋) → cta maintain --plan-only
  python scripts/demo_recording.py reset     # main으로 돌아가고 녹화 브랜치 삭제

장면 1(generate)은 준비가 필요 없다 — OrderService.delete에 테스트가 없는 상태가 main 그대로다.
실행 위치는 리포 루트 어디서나 되고, cta 명령은 examples/demo 안에서 친다.
"""

# ruff: noqa: E501 — 안내 문구·자바 코드 조각 줄은 100자 규칙을 적용하지 않는다

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "demo"
SERVICE = DEMO / "src/main/java/com/example/demo/order/OrderService.java"
PRICING = DEMO / "src/main/java/com/example/demo/pricing/PricingCalculator.java"
BRANCH = "demo-recording"

# 장면 2 — 버그 수정(null id 방어). findById는 호출자가 4곳(컨트롤러 1 + 같은 클래스 3)이라 --impact가 잘 보인다
SCENE2_OLD = (
    "        return repository.findById(id).orElseThrow(() -> new OrderNotFoundException(id));"
)
SCENE2_NEW = (
    '        if (id == null) {\n            throw new IllegalArgumentException("id required");\n        }\n'
    + SCENE2_OLD
)
SCENE2_MESSAGE = "fix: findById에 null id 방어 추가"

# 장면 3 — 리팩터링이라 했지만 스케일이 10 → 2로 바뀌어 동작이 달라진다 (기존 테스트 2건이 깨진다)
SCENE3_OLD = "        return subtotal.multiply(rate).setScale(10, RoundingMode.HALF_DOWN);"
SCENE3_NEW = (
    "        BigDecimal total = subtotal.multiply(rate);\n"
    "        return total.setScale(2, RoundingMode.HALF_DOWN);"
)
SCENE3_MESSAGE = "refactor: 금액 계산 결과를 변수로 분리해 정리"

# 장면 4 — 동작 보존 리팩터링(for → stream). 판단 메모 검색이 장면 3의 메모를 참고로 붙이는 걸 보여 준다
SCENE4_OLD = """        BigDecimal sum = BigDecimal.ZERO;
        for (Order order : orders) {
            if (order.getStatus() != OrderStatus.CANCELLED) {
                sum = sum.add(order.getAmount());
            }
        }
        return sum;"""
SCENE4_NEW = """        return orders.stream()
                .filter(order -> order.getStatus() != OrderStatus.CANCELLED)
                .map(Order::getAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);"""


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 실패:\n{result.stderr.strip()}")
    return result.stdout.strip()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(
            f"{path.name}에서 바꿀 코드를 찾지 못했다 — 이미 적용됐거나 순서가 어긋났다"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def clean_demo() -> None:
    """examples/demo를 커밋 상태로 되돌리고 .cta(제안·항목·메모·캐시)를 지운다."""
    git("checkout", "--", "examples/demo")
    git("clean", "-fdq", "--", "examples/demo")
    # .cta는 gitignore 대상이라 git clean(-x 없음)이 남긴다. 남은 제안·확인 항목이 다음 녹화의
    # generate에 "대기 중인 제안"으로 이어 붙고 resolve가 옛 항목을 집는다(2026-09-14 실측).
    # -x로 지우지 않는 이유: examples/demo/.env(게이트웨이 키)까지 지워진다
    shutil.rmtree(DEMO / ".cta", ignore_errors=True)


def prepare() -> None:
    current = git("branch", "--show-current")
    if current != BRANCH:
        if git("branch", "--list", BRANCH):
            git("checkout", "-q", BRANCH)
        else:
            git("checkout", "-q", "-b", BRANCH)
    clean_demo()
    print(f"브랜치 {BRANCH}, examples/demo 초기화 완료")
    print("Maven 예열 중 (의존성 캐시)...")
    warm = subprocess.run(
        ["mvn", "-B", "-q", "test", "-Dtest=OrderServiceTest"],
        cwd=DEMO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    print(
        "예열 완료"
        if warm.returncode == 0
        else f"예열 실패 — mvn이 PATH에 있는지 확인:\n{warm.stdout[-800:]}"
    )
    print("\n다음: cd examples/demo 에서 장면 1 명령을 친다 (시연영상_시나리오.md 맨 위 표)")


def scene2() -> None:
    replace_once(SERVICE, SCENE2_OLD, SCENE2_NEW)
    git("add", str(SERVICE.relative_to(REPO_ROOT)))
    git("commit", "-q", "-m", SCENE2_MESSAGE)
    print(f'장면 2 준비: findById null 방어 추가 + 커밋 "{SCENE2_MESSAGE}"')
    print("다음: cta maintain --diff HEAD~1 --impact")


def scene3() -> None:
    replace_once(PRICING, SCENE3_OLD, SCENE3_NEW)
    print("장면 3 준비: PricingCalculator 리팩터링(스케일 10 → 2, 미커밋)")
    print(
        f'다음: cta maintain --message "{SCENE3_MESSAGE}"  →  cta resolve <id> --intended  →  cta diff'
    )


def scene4() -> None:
    # 장면 3의 소스·적용된 테스트를 커밋해 두어야 장면 4의 diff에 total()만 잡힌다
    git("add", "--", "examples/demo/src")
    if git("diff", "--cached", "--name-only"):
        git("commit", "-q", "-m", SCENE3_MESSAGE)
    replace_once(SERVICE, SCENE4_OLD, SCENE4_NEW)
    print("장면 4 준비: 장면 3 커밋, total() 스트림 리팩터링(미커밋)")
    print('다음: cta maintain --message "refactor: 합계 계산을 스트림으로 정리" --plan-only')


def reset() -> None:
    clean_demo()
    git("checkout", "-q", "main")
    if git("branch", "--list", BRANCH):
        git("branch", "-D", BRANCH)
    print("main으로 복귀, 녹화 브랜치 삭제")


COMMANDS = {
    "prepare": prepare,
    "scene2": scene2,
    "scene3": scene3,
    "scene4": scene4,
    "reset": reset,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(1)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
