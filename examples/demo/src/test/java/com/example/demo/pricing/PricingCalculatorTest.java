package com.example.demo.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 기존 테스트 — 리팩터링 시나리오(SC-003)에서 동작 변경을 잡아내는 역할. */
class PricingCalculatorTest {

    private final PricingCalculator calculator = new PricingCalculator();

    @Test
    void calculate_emptyItems_returnsZero() {
        assertEquals(BigDecimal.ZERO, calculator.calculate(List.of(), new BigDecimal("1.5")));
    }

    @Test
    void calculate_singleItem_appliesRate() {
        List<LineItem> items = List.of(new LineItem("pen", 1, new BigDecimal("1000")));

        assertEquals(new BigDecimal("1500"), calculator.calculate(items, new BigDecimal("1.5")));
    }

    @Test
    void calculate_multipleItems_sumsBeforeRate() {
        List<LineItem> items = List.of(
                new LineItem("pen", 2, new BigDecimal("1000")),
                new LineItem("note", 1, new BigDecimal("500")));

        assertEquals(new BigDecimal("2500"), calculator.calculate(items, BigDecimal.ONE));
    }

    @Test
    void calculate_zeroQuantity_throws() {
        List<LineItem> items = List.of(new LineItem("pen", 0, new BigDecimal("1000")));

        assertThrows(IllegalArgumentException.class, () -> calculator.calculate(items, BigDecimal.ONE));
    }
}
