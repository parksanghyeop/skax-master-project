package com.example.demo.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 기존 테스트 — 이 팀의 테스트 작성 방식 본보기.
 * 저장소는 mock, 주문은 Order.builder()로 직접 만든다. 메서드 이름은 대상_상황_기대.
 * applyDiscount·total·updateAmount 등의 테스트는 일부러 없다(에이전트가 만들 몫).
 */
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository repository;

    @InjectMocks
    private OrderService service;

    @Test
    void create_validInput_savesNewOrder() {
        when(repository.save(any(Order.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Order saved = service.create("kim", new BigDecimal("5000"));

        assertEquals("kim", saved.getCustomerName());
        assertEquals(OrderStatus.NEW, saved.getStatus());
        verify(repository).save(any(Order.class));
    }

    @Test
    void create_blankCustomerName_throws() {
        assertThrows(IllegalArgumentException.class, () -> service.create("  ", BigDecimal.ONE));
    }

    @Test
    void findById_missing_throwsNotFound() {
        when(repository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(OrderNotFoundException.class, () -> service.findById(99L));
    }

    @Test
    void cancel_newOrder_setsCancelled() {
        Order order = Order.builder().id(1L).customerName("kim").amount(new BigDecimal("3000")).build();
        when(repository.findById(1L)).thenReturn(Optional.of(order));
        when(repository.save(any(Order.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Order cancelled = service.cancel(1L);

        assertEquals(OrderStatus.CANCELLED, cancelled.getStatus());
    }
}
