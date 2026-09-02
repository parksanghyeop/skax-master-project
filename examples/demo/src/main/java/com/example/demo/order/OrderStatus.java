package com.example.demo.order;

/** 주문 상태. NEW → PAID → (CANCELLED). 취소는 NEW·PAID에서만 가능하다. */
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
