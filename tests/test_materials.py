"""재료 수집(adapters/java/materials)의 단위 테스트 — 전부 파일 트리만으로 돈다.

검증: 확인 항목 열거(분기·경계값·예외·null), 메서드 선정(private·기존 참조 제외,
--max-methods 상한은 확인 항목 많은 순), 객체 생성법 판단(builder/값 객체/저장소 mock),
프롬프트 재료 렌더링, 확인 항목 충족 계산.
"""

from pathlib import Path

from cta.adapters.java.materials import (
    KIND_BOUNDARY,
    KIND_BRANCH,
    KIND_EXCEPTION,
    KIND_NULL,
    CheckItem,
    check_item_satisfaction,
    collect_materials,
    describe_construction,
    enumerate_check_items,
    parameter_types,
    render_materials,
    select_methods,
)
from cta.adapters.java.maven import detect_maven_project

SERVICE = """\
package com.example;

public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) { this.repository = repository; }

    public Order find(Long id) {
        return repository.findById(id).orElseThrow();
    }

    public BigDecimal applyDiscount(Order order, Customer customer, boolean isPromo) {
        if (order == null) {
            throw new IllegalArgumentException("order required");
        }
        BigDecimal amount = order.getAmount();
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        if (customer.getGrade() == Grade.GOLD && amount.compareTo(THRESHOLD) >= 0) {
            return amount.multiply(GOLD_RATE);
        }
        return isPromo ? amount.multiply(PROMO_RATE) : amount;
    }

    private int helper(int a) { return a; }
}
"""

EXISTING_TEST = """\
package com.example;
import org.junit.jupiter.api.Test;
class OrderServiceTest {
    @Test
    void find_missing_throws() { new OrderService(null).find(1L); }
}
"""


def _project(tmp_path: Path):
    main = tmp_path / "src" / "main" / "java" / "com" / "example"
    test = tmp_path / "src" / "test" / "java" / "com" / "example"
    main.mkdir(parents=True)
    test.mkdir(parents=True)
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (main / "OrderService.java").write_text(SERVICE, encoding="utf-8")
    (main / "Order.java").write_text(
        "public class Order { private Long id; public static Builder builder() { return null; }"
        " public static class Builder {} }",
        encoding="utf-8",
    )
    (main / "Customer.java").write_text(
        "public class Customer { private final String name;"
        " public Customer(String n) { name = n; } }",
        encoding="utf-8",
    )
    (main / "OrderRepository.java").write_text(
        "public interface OrderRepository extends JpaRepository<Order, Long> {}", encoding="utf-8"
    )
    (test / "OrderServiceTest.java").write_text(EXISTING_TEST, encoding="utf-8")
    return detect_maven_project(tmp_path), main / "OrderService.java"


class TestCheckItems:
    def test_분기_경계값_예외_null을_센다(self):
        method = next(m for m in _methods() if m.name == "applyDiscount")
        items = enumerate_check_items(method.text, 12)
        kinds = [i.kind for i in items]
        assert kinds.count(KIND_BRANCH) >= 3  # if 3개 + 삼항
        assert kinds.count(KIND_BOUNDARY) >= 2  # signum() < 0, compareTo >= 0
        assert kinds.count(KIND_EXCEPTION) == 2
        assert kinds.count(KIND_NULL) == 1
        assert all(i.line > 12 for i in items)  # 시그니처 줄은 제외, 줄 번호는 절대값


def _methods():
    from cta.adapters.java.parsing import extract_methods

    return extract_methods(SERVICE)


class TestSelectMethods:
    def test_private와_기존_참조_메서드를_건너뛴다(self, tmp_path):
        project, file = _project(tmp_path)
        selected, skipped = select_methods(project, file, max_methods=None)
        assert [m.name for m in selected] == ["applyDiscount"]
        reasons = dict(skipped)
        assert "private" in reasons["helper"]
        assert "기존 테스트" in reasons["find"]

    def test_상한은_확인_항목_많은_순으로_자른다(self, tmp_path):
        project, file = _project(tmp_path)
        selected, skipped = select_methods(project, file, max_methods=1, include_all=True)
        assert [m.name for m in selected] == ["applyDiscount"]  # find(0개)보다 항목이 많다
        assert any("max-methods" in why for _, why in skipped)

    def test_지정_메서드만_고르고_없는_이름은_보고한다(self, tmp_path):
        project, file = _project(tmp_path)
        selected, skipped = select_methods(project, file, None, only=["find", "nope"])
        assert [m.name for m in selected] == ["find"]
        assert ("nope", "클래스에 그 이름의 메서드가 없다") in skipped


class TestConstruction:
    def test_builder_값객체_저장소mock_표준타입을_구분한다(self, tmp_path):
        project, _ = _project(tmp_path)
        assert describe_construction(project, "Order").reason == "Order.builder() 사용"
        assert describe_construction(project, "Customer").reason == "값만 담는 객체"
        repo = describe_construction(project, "OrderRepository")
        assert repo.strategy == "mock 사용"
        assert "DB" in repo.reason
        assert describe_construction(project, "BigDecimal").reason == "표준 타입"

    def test_파라미터_타입을_제네릭_포함해_뽑는다(self):
        text = "public int f(List<Order> orders, Map<String, Integer> m, boolean flag) {"
        assert parameter_types(text) == ["List", "Map", "boolean"]


class TestMaterials:
    def test_재료를_한_번에_모아_프롬프트_재료로_만든다(self, tmp_path):
        project, file = _project(tmp_path)
        selected, skipped = select_methods(project, file, None)
        materials = collect_materials(project, file, selected, skipped, "OrderServiceTest")
        names = [c.type_name for c in materials.constructions]
        assert names == ["Order", "Customer", "boolean", "OrderRepository"]  # 파라미터 + 필드 의존
        assert materials.existing_test_code.startswith("package com.example;")
        assert materials.target_lines  # 커버리지 판정 라인
        rendered = render_materials(materials)
        assert "[확인해야 할 항목" in rendered
        assert "OrderRepository → mock 사용" in rendered
        assert "기존 테스트 파일" in rendered

    def test_확인_항목_충족은_실행된_줄과_분기_완전_실행으로_센다(self):
        items = [
            CheckItem(KIND_BRANCH, 10, "if"),
            CheckItem(KIND_EXCEPTION, 11, "throw"),
            CheckItem(KIND_BOUNDARY, 12, ">="),
        ]
        coverage = {
            10: {"ci": 1, "mb": 1, "cb": 1},  # 분기 절반만 실행 → 미충족
            11: {"ci": 1, "mb": 0, "cb": 0},  # 실행됨 → 충족
            12: {"ci": 0, "mb": 0, "cb": 0},  # 미실행 → 미충족
        }
        assert check_item_satisfaction(items, coverage) == 1
