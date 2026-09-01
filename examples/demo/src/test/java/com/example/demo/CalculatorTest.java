package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/**
 * 기존 테스트 — 프로젝트의 테스트 스타일 본보기이자 M1 예열·오프라인 실행 대상.
 * divide의 테스트는 일부러 없다 (M3에서 에이전트가 만들 몫).
 */
class CalculatorTest {

    @Test
    void add_twoPositives_returnsSum() {
        Calculator calculator = new Calculator();
        assertEquals(7, calculator.add(3, 4));
    }

    @Test
    void add_negativeAndPositive_returnsSum() {
        Calculator calculator = new Calculator();
        assertEquals(-1, calculator.add(-4, 3));
    }
}
