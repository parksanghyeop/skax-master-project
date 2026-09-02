"""게이트 ④⑤ 실측 불변식 — 실제 Docker 필요 (marker: docker).

핵심 불변식(phase2 스킬): "assert 없는 100% 커버리지 테스트"는 커버리지 게이트를
속일 수 있어도 **뮤테이션 게이트에서 탈락**해야 한다.
사전 조건: examples/demo의 의존성 캐시가 PIT 예열 포함으로 준비돼 있어야 한다
(캐시 삭제 후 아무 CLI나 실행하면 준비된다).
"""

from pathlib import Path

import pytest

from cta.adapters.java.gates import CoverageGate
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.mutation import MutationGate
from cta.adapters.java.parsing import method_line_spans
from cta.core.gates import GateConfig
from cta.sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "demo"
CACHE = DEMO / ".cta" / "m2repo"
ORDER_DIR = DEMO / "src" / "main" / "java" / "com" / "example" / "demo" / "order"

# assert가 하나도 없는 "실행만 하는" 테스트 — 라인은 커버하지만 아무것도 검증 안 함.
# total은 저장소를 쓰지 않아 mock 없이 호출할 수 있다.
ASSERTLESS_TEST = """\
package com.example.demo.order;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderServiceAssertlessTest {

    @Test
    void total_runsWithoutChecking() {
        OrderService service = new OrderService(null);
        Order kept = Order.builder().customerName("a").amount(new BigDecimal("100")).build();
        Order cancelled = Order.builder().customerName("b").amount(new BigDecimal("50"))
                .status(OrderStatus.CANCELLED).build();
        service.total(List.of(kept, cancelled));
        service.total(List.of());
    }
}
"""

TEST_PATH = (
    DEMO
    / "src"
    / "test"
    / "java"
    / "com"
    / "example"
    / "demo"
    / "order"
    / "OrderServiceAssertlessTest.java"
)


@pytest.mark.docker
def test_불변식4_assert_없는_테스트는_커버리지를_채워도_뮤테이션에서_탈락한다():
    project = detect_maven_project(DEMO)
    sandbox = DockerSandbox()
    source = (ORDER_DIR / "OrderService.java").read_text(encoding="utf-8")
    span = next(s for s in method_line_spans(source) if s.name == "total")
    total_lines = set(range(span.start_line, span.end_line + 1))
    try:
        TEST_PATH.write_text(ASSERTLESS_TEST, encoding="utf-8")

        coverage = CoverageGate(
            project,
            sandbox,
            CACHE,
            "OrderServiceAssertlessTest",
            "OrderService.java",
            total_lines,
            GateConfig(),
        ).check()
        assert coverage.passed is True, coverage.reason  # 실행만으로 커버리지는 채워진다

        mutation = MutationGate(
            project,
            sandbox,
            CACHE,
            "com.example.demo.order.OrderService",
            "com.example.demo.order.OrderServiceAssertlessTest",
            0.5,
            target_methods={"total"},
        ).check()
        assert mutation.passed is False, mutation.reason  # 심은 버그를 하나도 못 잡는다
    finally:
        TEST_PATH.unlink(missing_ok=True)
