package com.example.demo.order;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

/** 주문 저장소 — DB에 접근하는 인터페이스. 단위 테스트에서는 mock으로 대체한다. */
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByCustomerName(String customerName);
}
