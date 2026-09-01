package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class CalculatorAddTest {

    @Test
    void addsTwoPositiveNumbers() {
        Calculator calc = new Calculator();
        assertEquals(5, calc.add(2, 3));
        assertEquals(42, calc.add(19, 23));
    }

    @Test
    void addsWithZero() {
        Calculator calc = new Calculator();
        assertEquals(7, calc.add(7, 0));
        assertEquals(7, calc.add(0, 7));
        assertEquals(0, calc.add(0, 0));
    }

    @Test
    void addsWithNegativeNumbers() {
        Calculator calc = new Calculator();
        assertEquals(-7, calc.add(-2, -5));
        assertEquals(3, calc.add(-2, 5));
        assertEquals(3, calc.add(5, -2));
        assertEquals(-3, calc.add(-5, 2));
    }
}
