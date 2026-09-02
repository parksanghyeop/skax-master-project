package com.example.demo.order;

import com.example.demo.customer.Customer;
import com.example.demo.customer.Grade;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * 주문 CRUD와 금액 계산을 담당하는 서비스.
 * create/findById/cancel은 기존 테스트가 있고, 나머지(applyDiscount, total,
 * updateAmount, pay, delete ...)는 테스트가 없다 — 테스트 생성 시나리오(SC-001)의 대상.
 */
@Service
public class OrderService {

    /** 등급 할인이 적용되는 최소 주문 금액(이상). */
    static final BigDecimal THRESHOLD = new BigDecimal("10000");
    static final BigDecimal GOLD_RATE = new BigDecimal("0.85");
    static final BigDecimal PROMO_RATE = new BigDecimal("0.95");

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order create(String customerName, BigDecimal amount) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException("customerName required");
        }
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        Order order = Order.builder().customerName(customerName).amount(amount).build();
        return repository.save(order);
    }

    public Order findById(Long id) {
        return repository.findById(id).orElseThrow(() -> new OrderNotFoundException(id));
    }

    public List<Order> findAll() {
        return repository.findAll();
    }

    public List<Order> findByCustomer(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException("customerName required");
        }
        return repository.findByCustomerName(customerName);
    }

    public Order updateAmount(Long id, BigDecimal amount) {
        Order order = findById(id);
        if (order.getStatus() != OrderStatus.NEW) {
            throw new IllegalStateException("only NEW orders can be changed");
        }
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        order.setAmount(amount);
        return repository.save(order);
    }

    public Order pay(Long id) {
        Order order = findById(id);
        if (order.getStatus() != OrderStatus.NEW) {
            throw new IllegalStateException("only NEW orders can be paid");
        }
        order.setStatus(OrderStatus.PAID);
        return repository.save(order);
    }

    public Order cancel(Long id) {
        Order order = findById(id);
        if (order.getStatus() == OrderStatus.CANCELLED) {
            throw new IllegalStateException("already cancelled");
        }
        order.setStatus(OrderStatus.CANCELLED);
        return repository.save(order);
    }

    public void delete(Long id) {
        if (!repository.existsById(id)) {
            throw new OrderNotFoundException(id);
        }
        repository.deleteById(id);
    }

    /**
     * 할인 적용 금액. GOLD 등급이 임계금액 이상 주문하면 등급 할인,
     * 아니면 프로모션 여부에 따라 프로모션 할인 또는 원금.
     */
    public BigDecimal applyDiscount(Order order, Customer customer, boolean isPromo) {
        if (order == null) {
            throw new IllegalArgumentException("order required");
        }
        if (customer == null) {
            throw new IllegalArgumentException("customer required");
        }
        BigDecimal amount = order.getAmount();
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        if (customer.getGrade() == Grade.GOLD && amount.compareTo(THRESHOLD) >= 0) {
            return amount.multiply(GOLD_RATE);
        }
        return isPromo ? amount.multiply(PROMO_RATE) : amount;
    }

    /** 취소되지 않은 주문들의 총액. */
    public BigDecimal total(List<Order> orders) {
        // 주문 총액을 계산한다
        BigDecimal sum = BigDecimal.ZERO;
        for (Order order : orders) {
            if (order.getStatus() != OrderStatus.CANCELLED) {
                sum = sum.add(order.getAmount());
            }
        }
        return sum;
    }
}
