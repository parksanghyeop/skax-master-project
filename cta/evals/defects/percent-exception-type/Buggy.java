package com.example.bench;

import java.util.Arrays;

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

    /** 중앙값. 입력 순서와 무관하다(정렬 후 계산). 짝수 개면 가운데 두 값의 평균. null·빈 배열은 IllegalArgumentException. */
    public double median(int[] values) {
        if (values == null || values.length == 0) {
            throw new IllegalArgumentException("값이 없다");
        }
        int[] sorted = values.clone();
        Arrays.sort(sorted);
        int mid = sorted.length / 2;
        if (sorted.length % 2 == 1) {
            return sorted[mid];
        }
        return (sorted[mid - 1] + sorted[mid]) / 2.0;
    }

    /** part가 total의 몇 퍼센트인지 정수로 반올림. total이 0 이하면 IllegalArgumentException. */
    public int percent(int part, int total) {
        return (int) Math.round(part * 100.0 / total);
    }
}
