package com.example.demo;

/**
 * 간단한 계산기 — PoC의 테스트 생성 대상.
 * divide는 일부러 테스트가 없는 상태로 둔다: M3에서 에이전트가
 * "예외 경로가 있는 미검증 메서드"에 테스트를 만들어 보는 표적이다.
 */
public class Calculator {

    public int add(int a, int b) {
        return a + b;
    }

    /**
     * 정수 나눗셈. 0으로 나누면 IllegalArgumentException을 던진다.
     */
    public int divide(int dividend, int divisor) {
        if (divisor == 0) {
            throw new IllegalArgumentException("0으로 나눌 수 없다");
        }
        return dividend / divisor;
    }
}
