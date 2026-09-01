package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public class CalculatorDivideTest {

    @Test
    void divide_byZero_throwsIllegalArgumentException() {
        Calculator calculator = new Calculator();
        IllegalArgumentException ex =
                assertThrows(IllegalArgumentException.class, () -> calculator.divide(1, 0));
        assertEquals("0으로 나눌 수 없다", ex.getMessage());
    }

    @Test
    void divide_dividendHasRemainder_truncatesTowardZero() {
        Calculator calculator = new Calculator();
        assertEquals(2, calculator.divide(7, 3));
    }

    @Test
    void divide_negativeDividend_truncatesTowardZero() {
        Calculator calculator = new Calculator();
        assertEquals(-2, calculator.divide(-7, 3));
    }

    @Test
    void divide_negativeDivisor_truncatesTowardZero() {
        Calculator calculator = new Calculator();
        assertEquals(-2, calculator.divide(7, -3));
    }

    @Test
    void divide_zeroDividend_returnsZero() {
        Calculator calculator = new Calculator();
        assertEquals(0, calculator.divide(0, 5));
    }
}
