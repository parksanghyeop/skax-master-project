package com.example.bench;

public class MathUtil {

    public int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min이 max보다 크다");
        }
        if (value < min) {
            return min;
        }
        return Math.max(value, max);
    }

    public int divideRounded(int dividend, int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("0으로 나눌 수 없다");
        }
        long scaled = (long) dividend * 2;
        long q = scaled / divisor;
        long adjusted = q >= 0 ? q + 1 : q - 1;
        return (int) (adjusted / 2);
    }

    public long fibonacci(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("음수 불가");
        }
        if (n < 2) {
            return n;
        }
        long a = 0;
        long b = 1;
        for (int i = 2; i <= n; i++) {
            long next = a + b;
            a = b;
            b = next;
        }
        return b;
    }
}
