"""시나리오 재현용 작업 저장소 만들기 — SC-002(버그 수정 커밋)·SC-003(리팩터링 커밋).

examples/demo는 이 리포의 하위 폴더라 시나리오용 커밋을 만들면 리포 이력이 더러워진다.
그래서 데모를 임시 폴더에 복사해 독립 git 저장소로 만들고, 시나리오에 맞는 커밋을
쌓아 둔다. 의존성 캐시(.cta/m2repo)는 함께 복사해 준비 단계를 다시 돌지 않게 한다.

사용:
  python scripts/demo_scenarios.py bugfix   <출력폴더>   # SC-002: v1(버그) → v2(fix 커밋)
  python scripts/demo_scenarios.py refactor <출력폴더>   # SC-003: v1 → 스트림 리팩터링 커밋
그 다음:  cd <출력폴더> && cta maintain --diff HEAD~1
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "demo"
SERVICE = Path("src/main/java/com/example/demo/order/OrderService.java")
PRICING = Path("src/main/java/com/example/demo/pricing/PricingCalculator.java")

# SC-002: v1은 경계 조건 버그(> — 임계금액과 같으면 할인이 빠짐), v2가 >=로 고친 커밋
BUGGY_CONDITION = "amount.compareTo(THRESHOLD) > 0"
FIXED_CONDITION = "amount.compareTo(THRESHOLD) >= 0"
BUGFIX_MESSAGE = "fix: 할인 임계금액 경계 조건 오류 수정 (#4821)"

# SC-003: for문을 스트림으로 바꾸다 빈 목록 처리가 빠진 "동작이 바뀐 리팩터링"
LOOP_BODY = """\
        if (items == null || items.isEmpty()) {
            return BigDecimal.ZERO;
        }
        BigDecimal subtotal = BigDecimal.ZERO;
        for (LineItem item : items) {
            if (item.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            subtotal = subtotal.add(item.unitPrice().multiply(BigDecimal.valueOf(item.quantity())));
        }
        return subtotal.multiply(rate).setScale(0, RoundingMode.HALF_UP);
"""
STREAM_BODY = """\
        return items.stream()
                .peek(item -> {
                    if (item.quantity() <= 0) {
                        throw new IllegalArgumentException("quantity must be positive");
                    }
                })
                .map(item -> item.unitPrice().multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal::add)
                .map(subtotal -> subtotal.multiply(rate).setScale(0, RoundingMode.HALF_UP))
                .orElse(null);
"""
REFACTOR_MESSAGE = "refactor: calculate를 스트림으로 정리"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=demo@example.com", "-c", "user.name=demo"]
        + list(args),
        check=True,
        capture_output=True,
    )


def _copy_demo(out: Path) -> None:
    if out.exists():
        raise SystemExit(f"출력 폴더가 이미 있다: {out} — 지우고 다시 실행하라")
    ignored = shutil.ignore_patterns("target", "pom-cta-pit.xml", "proposals", "escalations")
    shutil.copytree(DEMO, out, ignore=ignored)
    _git(out, "init", "-q")
    (out / ".gitignore").write_text(".cta/\ntarget/\npom-cta-pit.xml\n.env\n", encoding="utf-8")


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"{path}에서 바꿀 부분을 찾지 못했다: {old[:40]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def bugfix(out: Path) -> None:
    _copy_demo(out)
    service = out / SERVICE
    _replace(service, FIXED_CONDITION, BUGGY_CONDITION)  # v1: 버그 있는 상태
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: 주문 서비스 초기 구현")
    _replace(service, BUGGY_CONDITION, FIXED_CONDITION)  # v2: 고침
    # 주석만 바뀐 변경 — 의미 없는 변경(trivial) 판정의 예
    _replace(service, "// 주문 총액을 계산한다", "// 총액 계산 (취소 주문 제외)")
    _git(out, "commit", "-q", "-am", BUGFIX_MESSAGE)
    print(f"SC-002 준비 완료: {out}\n  cd {out} && cta maintain --diff HEAD~1")


def refactor(out: Path) -> None:
    _copy_demo(out)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: 가격 계산기 초기 구현")
    _replace(out / PRICING, LOOP_BODY, STREAM_BODY)
    _git(out, "commit", "-q", "-am", REFACTOR_MESSAGE)
    print(f"SC-003 준비 완료: {out}\n  cd {out} && cta maintain --diff HEAD~1")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("bugfix", "refactor"):
        print(__doc__)
        raise SystemExit(2)
    {"bugfix": bugfix, "refactor": refactor}[sys.argv[1]](Path(sys.argv[2]).resolve())
