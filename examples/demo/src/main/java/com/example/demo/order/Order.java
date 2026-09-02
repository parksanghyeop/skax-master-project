package com.example.demo.order;

import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

/** 주문 엔티티. 생성은 {@link #builder()}로 한다. */
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String customerName;

    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected Order() {
        // JPA 전용
    }

    private Order(Builder builder) {
        this.id = builder.id;
        this.customerName = builder.customerName;
        this.amount = builder.amount;
        this.status = builder.status;
    }

    public static Builder builder() {
        return new Builder();
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    /** 주문 빌더 — 기본 상태는 NEW, 기본 금액은 0. */
    public static class Builder {
        private Long id;
        private String customerName;
        private BigDecimal amount = BigDecimal.ZERO;
        private OrderStatus status = OrderStatus.NEW;

        public Builder id(Long id) {
            this.id = id;
            return this;
        }

        public Builder customerName(String customerName) {
            this.customerName = customerName;
            return this;
        }

        public Builder amount(BigDecimal amount) {
            this.amount = amount;
            return this;
        }

        public Builder status(OrderStatus status) {
            this.status = status;
            return this;
        }

        public Order build() {
            return new Order(this);
        }
    }
}
