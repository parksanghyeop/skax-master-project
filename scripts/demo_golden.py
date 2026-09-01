"""대표 검증 시나리오 시연 스크립트 — 저장된 LLM 호출 기록을 재생해 전체 흐름을 출력한다.

산출물(핵심 동작 검증)과 발표 데모에 쓴다. LLM 비용 0(실호출 없음), Docker 필요.
실행: .venv/Scripts/python scripts/demo_golden.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from core.writer_graph import build_writer_graph  # noqa: E402
from evals import golden_case as gc  # noqa: E402
from llm.replay import ReplayClient  # noqa: E402


def main() -> None:
    print("=== Code Test Agent — 대표 검증 시나리오 시연 ===")
    print(f"대상: {gc.TARGET}  (테스트가 없는 divide 메서드)")
    print(f"지침: {gc.INSTRUCTION}")
    print(f"LLM: 실호출 없음 — 저장된 호출 기록을 재생 (기록된 모델: {gc.cassette_model()})")
    print()
    started = time.monotonic()
    try:
        ports = gc.make_ports(ReplayClient(gc.CASSETTE))
        final = build_writer_graph(ports).invoke(gc.initial_state())
        elapsed = time.monotonic() - started

        print("[1] inspect_target  → 대상 조사 (Calculator.java에서 divide 확인)")
        print("[2] query_code_graph→ 비슷한 모양의 기존 테스트 2건을 본보기로 수집")
        print(f"[3] LLM 생성        → {len(final['test_code'])}자 테스트 코드")
        print(f"[4] write_test      → {final['write_result']}")
        print(f"[5] run_tests       → {final['last_run'].splitlines()[0]}", end="")
        stats = [ln for ln in final["last_run"].splitlines() if "Tests run:" in ln]
        print(f" / {stats[0].strip()}" if stats else "")
        print(f"[6] check_quality   → {final['quality']}")
        print()
        print(f"최종 상태: {final['status']}  (시도 {final['attempts']}회, {elapsed:.1f}초)")
        print()
        print("--- 생성된 테스트 (CalculatorDivideTest.java) ---")
        print(final["test_code"])
    finally:
        gc.TEST_PATH.unlink(missing_ok=True)  # 시연 후 생성물 정리 — 반복 실행 가능하게


if __name__ == "__main__":
    main()
