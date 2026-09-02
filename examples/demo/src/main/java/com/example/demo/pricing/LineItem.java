package com.example.demo.pricing;

import java.math.BigDecimal;

/** 가격 계산의 입력 한 줄 — 상품명, 수량, 단가. */
public record LineItem(String productName, int quantity, BigDecimal unitPrice) {}
