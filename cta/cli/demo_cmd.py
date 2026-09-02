"""cta demo — 대표 검증 시나리오를 저장된 LLM 호출 기록으로 재생해 보여준다.

LLM 비용 0(실호출 없음), Docker 필요. 산출물 캡처·발표 데모용.
대상: examples/demo(Spring Boot 주문 CRUD)의 OrderService#applyDiscount.
"""

import time

from cta.core.writer_graph import build_writer_graph
from cta.evals import golden_case as gc
from cta.llm.replay import ReplayClient


def run_demo(args) -> int:
    # 개발 리포 전용 — 예제 프로젝트·저장된 호출 기록이 리포에 있어야 돈다
    if not gc.CASSETTE.is_file() or not gc.DEMO_PROJECT.is_dir():
        print("cta demo는 개발 리포지토리 안에서만 동작한다 (예제·호출 기록 필요).")
        print("일반 사용은 cta generate / cta maintain을 쓰라.")
        return 1
    print("=== Code Test Agent — 대표 검증 시나리오 시연 ===")
    print(f"대상: {gc.TARGET}  (테스트가 없는 할인 계산 메서드)")
    print(f"지침: {gc.INSTRUCTION}")
    print(f"LLM: 실호출 없음 — 저장된 호출 기록을 재생 (기록된 모델: {gc.cassette_model()})")
    print()
    started = time.monotonic()
    try:
        ports = gc.make_ports(ReplayClient(gc.CASSETTE))
        final = build_writer_graph(ports).invoke(gc.initial_state())
        elapsed = time.monotonic() - started

        print("[1] inspect_target  → 대상 조사 (OrderService.java에서 applyDiscount 확인)")
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
        print(f"--- 생성된 테스트 ({gc.SELECTOR}.java) ---")
        print(final["test_code"])
        return 0
    finally:
        gc.TEST_PATH.unlink(missing_ok=True)  # 시연 후 생성물 정리 — 반복 실행 가능하게
