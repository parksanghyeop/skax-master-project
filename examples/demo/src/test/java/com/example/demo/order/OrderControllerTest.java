package com.example.demo.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderControllerTest {

    @Autowired
    private OrderController controller;

    @Test
    @DisplayName("findById null 방어 로직: OrderController#get(null) 호출 시 IllegalArgumentException 전파")
    void get_nullId_throwsIllegalArgumentException_propagatedFromService() {
        assertThrows(IllegalArgumentException.class, () -> controller.get(null));
    }

    @Test
    @DisplayName("findById 기존 동작 유지: 유효한 id로 OrderController#get 호출 시 해당 주문 반환")
    void get_validId_returnsOrder_asBeforeChange() {
        OrderController.CreateOrderRequest req = new OrderController.CreateOrderRequest("alice", new BigDecimal("123.45"));
        Order created = controller.create(req);
        assertNotNull(created);
        assertNotNull(created.getId());

        Order fetched = controller.get(created.getId());
        assertNotNull(fetched);
        assertEquals(created.getId(), fetched.getId());
        assertEquals("alice", fetched.getCustomerName());
        assertEquals(new BigDecimal("123.45"), fetched.getAmount());
    }
}
