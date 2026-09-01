package com.example.bench;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MathUtilClampTest {

    @Test
    void clamp_insideRange_returnsValue() {
        MathUtil util = new MathUtil();
        assertEquals(5, util.clamp(5, 0, 10));
    }

    @Test
    void clamp_belowRange_returnsMin() {
        MathUtil util = new MathUtil();
        assertEquals(0, util.clamp(-1, 0, 10));
    }

    @Test
    void clamp_aboveRange_returnsMax() {
        MathUtil util = new MathUtil();
        assertEquals(10, util.clamp(11, 0, 10));
    }

    @Test
    void clamp_valueEqualToMin_returnsMin() {
        MathUtil util = new MathUtil();
        assertEquals(3, util.clamp(3, 3, 7));
    }

    @Test
    void clamp_valueEqualToMax_returnsMax() {
        MathUtil util = new MathUtil();
        assertEquals(7, util.clamp(7, 3, 7));
    }

    @Test
    void clamp_negativeRange_inside_returnsValue() {
        MathUtil util = new MathUtil();
        assertEquals(-5, util.clamp(-5, -10, -1));
    }

    @Test
    void clamp_negativeRange_belowMin_returnsMin() {
        MathUtil util = new MathUtil();
        assertEquals(-10, util.clamp(-11, -10, -1));
    }

    @Test
    void clamp_equalBounds_returnsBound() {
        MathUtil util = new MathUtil();
        assertEquals(4, util.clamp(100, 4, 4));
    }

    @Test
    void clamp_minGreaterThanMax_throwsIllegalArgumentException() {
        MathUtil util = new MathUtil();
        assertThrows(IllegalArgumentException.class, () -> util.clamp(0, 5, 3));
    }

    @Test
    void clamp_fullIntRange_noClampNeeded_returnsValue() {
        MathUtil util = new MathUtil();
        assertEquals(123, util.clamp(123, Integer.MIN_VALUE, Integer.MAX_VALUE));
    }
}
