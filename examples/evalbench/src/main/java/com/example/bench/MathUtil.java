package com.example.bench;

/**
 * 수 계산 유틸 — 평가 하네스의 대상 클래스 2 (고친 버전).
 * 각 메서드는 evals/defects/의 버그 버전과 짝을 이룬다.
 */
public class MathUtil {

    /** min~max(양끝 포함)로 값을 고정한다. min > max면 IllegalArgumentException. */
    public int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min이 max보다 크다");
        }
        if (value < min) {
            return min;
        }
        return Math.min(value, max);
    }

    /** 정수 나눗셈을 반올림한다 (음수 포함). divisor가 0이면 ArithmeticException. */
    public int divideRounded(int dividend, int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("0으로 나눌 수 없다");
        }
        long scaled = (long) dividend * 2;
        long q = scaled / divisor;
        long adjusted = q >= 0 ? q + 1 : q - 1;
        return (int) (adjusted / 2);
    }

    /** n번째 피보나치 수 (0번=0, 1번=1). 음수면 IllegalArgumentException. */
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
