package com.example.demo.pricing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * 품목 목록의 금액을 계산한다. 기존 테스트(PricingCalculatorTest)가 있어
 * 리팩터링 시나리오(SC-003: 동작이 바뀌면 테스트가 깨진다)의 대상이다.
 */
@Component
public class PricingCalculator {

    /** 품목 합계에 rate를 곱해 정수 원 단위로 반올림한다. 품목이 없으면 0. */
    public BigDecimal calculate(List<LineItem> items, BigDecimal rate) {
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
        return subtotal.multiply(rate).setScale(10, RoundingMode.HALF_DOWN);
    }
}
