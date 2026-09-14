package com.example.demo.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.demo.customer.Customer;
import com.example.demo.customer.Grade;
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.never;

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

    // findByCustomer tests
    @Test
    void findByCustomer_validName_returnsOrders() {
        Order o1 = Order.builder().id(1L).customerName("kim").amount(new BigDecimal("1000")).build();
        Order o2 = Order.builder().id(2L).customerName("kim").amount(new BigDecimal("2000")).build();
        List<Order> expected = Arrays.asList(o1, o2);
        when(repository.findByCustomerName("kim")).thenReturn(expected);

        List<Order> result = service.findByCustomer("kim");

        assertEquals(2, result.size());
        assertEquals("kim", result.get(0).getCustomerName());
        assertEquals("kim", result.get(1).getCustomerName());
    }

    @Test
    void findByCustomer_blankName_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.findByCustomer("  "));
    }

    @Test
    void findByCustomer_nullName_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.findByCustomer(null));
    }

    // updateAmount tests
    @Test
    void updateAmount_notNewOrder_throwsIllegalState() {
        Order existing = Order.builder()
                .id(10L)
                .customerName("lee")
                .amount(new BigDecimal("3000"))
                .status(OrderStatus.PAID)
                .build();
        when(repository.findById(10L)).thenReturn(Optional.of(existing));

        assertThrows(IllegalStateException.class, () -> service.updateAmount(10L, new BigDecimal("2000")));
    }

    @Test
    void updateAmount_nullAmount_throwsIllegalArgument() {
        Order existing = Order.builder()
                .id(11L)
                .customerName("lee")
                .amount(new BigDecimal("3000"))
                .status(OrderStatus.NEW)
                .build();
        when(repository.findById(11L)).thenReturn(Optional.of(existing));

        assertThrows(IllegalArgumentException.class, () -> service.updateAmount(11L, null));
    }

    @Test
    void updateAmount_negativeAmount_throwsIllegalArgument() {
        Order existing = Order.builder()
                .id(12L)
                .customerName("park")
                .amount(new BigDecimal("3000"))
                .status(OrderStatus.NEW)
                .build();
        when(repository.findById(12L)).thenReturn(Optional.of(existing));

        assertThrows(IllegalArgumentException.class, () -> service.updateAmount(12L, new BigDecimal("-1")));
    }

    @Test
    void updateAmount_zeroAmount_updatesSuccessfully() {
        Order existing = Order.builder()
                .id(13L)
                .customerName("choi")
                .amount(new BigDecimal("3000"))
                .status(OrderStatus.NEW)
                .build();
        when(repository.findById(13L)).thenReturn(Optional.of(existing));
        when(repository.save(any(Order.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Order updated = service.updateAmount(13L, BigDecimal.ZERO);

        assertEquals(0, updated.getAmount().compareTo(BigDecimal.ZERO));
        verify(repository).save(any(Order.class));
    }

    @Test
    void updateAmount_positiveAmount_updatesSuccessfully() {
        Order existing = Order.builder()
                .id(14L)
                .customerName("han")
                .amount(new BigDecimal("100"))
                .status(OrderStatus.NEW)
                .build();
        when(repository.findById(14L)).thenReturn(Optional.of(existing));
        when(repository.save(any(Order.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Order updated = service.updateAmount(14L, new BigDecimal("250"));

        assertEquals(new BigDecimal("250"), updated.getAmount());
        verify(repository).save(any(Order.class));
    }

    // pay tests
    @Test
    void pay_notNewOrder_throwsIllegalState() {
        Order existing = Order.builder()
                .id(20L)
                .customerName("kim")
                .amount(new BigDecimal("1500"))
                .status(OrderStatus.CANCELLED)
                .build();
        when(repository.findById(20L)).thenReturn(Optional.of(existing));

        assertThrows(IllegalStateException.class, () -> service.pay(20L));
    }

    @Test
    void pay_newOrder_setsPaid() {
        Order existing = Order.builder()
                .id(21L)
                .customerName("kim")
                .amount(new BigDecimal("1500"))
                .status(OrderStatus.NEW)
                .build();
        when(repository.findById(21L)).thenReturn(Optional.of(existing));
        when(repository.save(any(Order.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Order paid = service.pay(21L);

        assertEquals(OrderStatus.PAID, paid.getStatus());
        verify(repository).save(any(Order.class));
    }

    // applyDiscount tests
    @Test
    void applyDiscount_nullOrder_throwsIllegalArgument() {
        Customer customer = new Customer("kim", Grade.BASIC);

        assertThrows(IllegalArgumentException.class, () -> service.applyDiscount(null, customer, false));
    }

    @Test
    void applyDiscount_nullCustomer_throwsIllegalArgument() {
        Order order = Order.builder().id(30L).customerName("kim").amount(new BigDecimal("100")).build();

        assertThrows(IllegalArgumentException.class, () -> service.applyDiscount(order, null, false));
    }

    @Test
    void applyDiscount_negativeAmount_throwsIllegalArgument() {
        Order order = Order.builder().id(31L).customerName("kim").amount(new BigDecimal("-1")).build();
        Customer customer = new Customer("kim", Grade.BASIC);

        assertThrows(IllegalArgumentException.class, () -> service.applyDiscount(order, customer, false));
    }

    @Test
    void applyDiscount_goldAtThreshold_usesGoldRate() {
        Order order = Order.builder().id(32L).customerName("gold").amount(new BigDecimal("10000")).build();
        Customer customer = new Customer("gold", Grade.GOLD);

        BigDecimal result = service.applyDiscount(order, customer, true);

        BigDecimal expected = new BigDecimal("10000").multiply(new BigDecimal("0.85"));
        assertEquals(expected, result);
    }

    @Test
    void applyDiscount_goldBelowThreshold_withPromo_usesPromoRate() {
        Order order = Order.builder().id(33L).customerName("gold").amount(new BigDecimal("9000")).build();
        Customer customer = new Customer("gold", Grade.GOLD);

        BigDecimal result = service.applyDiscount(order, customer, true);

        BigDecimal expected = new BigDecimal("9000").multiply(new BigDecimal("0.95"));
        assertEquals(expected, result);
    }

    @Test
    void applyDiscount_nonGold_noPromo_returnsOriginal() {
        Order order = Order.builder().id(34L).customerName("silver").amount(new BigDecimal("7000")).build();
        Customer customer = new Customer("silver", Grade.SILVER);

        BigDecimal result = service.applyDiscount(order, customer, false);

        assertEquals(new BigDecimal("7000"), result);
    }

    @Test
    void delete_nonExistingId_throwsNotFound() {
        when(repository.existsById(100L)).thenReturn(false);

        assertThrows(OrderNotFoundException.class, () -> service.delete(100L));
    }

    @Test
    void delete_existsCheck_falseBranch_throwsOrderNotFoundException() {
        when(repository.existsById(101L)).thenReturn(false);

        assertThrows(OrderNotFoundException.class, () -> service.delete(101L));
    }

    @Test
    void delete_existingId_callsRepositoryDeleteById() {
        when(repository.existsById(200L)).thenReturn(true);

        service.delete(200L);

        verify(repository).deleteById(200L);
    }

    @Test
    void findById_nullId_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.findById(null));
    }

    @Test
    void findById_existingId_returnsOrder() {
        Order order = Order.builder().id(2L).customerName("kim").amount(new BigDecimal("500")).build();
        when(repository.findById(2L)).thenReturn(Optional.of(order));

        Order found = service.findById(2L);

        assertEquals(2L, found.getId());
        assertEquals("kim", found.getCustomerName());
    }

    @Test
    void pay_nullId_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.pay(null));
    }

    @Test
    void cancel_alreadyCancelled_throwsIllegalState() {
        Order existing = Order.builder()
                .id(15L)
                .customerName("kim")
                .amount(new BigDecimal("3000"))
                .status(OrderStatus.CANCELLED)
                .build();
        when(repository.findById(15L)).thenReturn(Optional.of(existing));

        assertThrows(IllegalStateException.class, () -> service.cancel(15L));
    }

    @Test
    void cancel_nullId_throwsIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> service.cancel(null));
    }

    @Test
    void pay_nullId_throwsIllegalArgument_withoutRepositoryInteraction() {
        assertThrows(IllegalArgumentException.class, () -> service.pay(null));

        verify(repository, never()).findById(any());
        verify(repository, never()).save(any(Order.class));
    }

    @Test
    void total_mixedStatuses_sumsOnlyNonCancelled() {
        Order o1 = Order.builder().id(101L).customerName("kim").amount(new BigDecimal("1000")).status(OrderStatus.NEW).build();
        Order o2 = Order.builder().id(102L).customerName("kim").amount(new BigDecimal("2000")).status(OrderStatus.CANCELLED).build();
        Order o3 = Order.builder().id(103L).customerName("kim").amount(new BigDecimal("3000")).status(OrderStatus.PAID).build();
        List<Order> orders = Arrays.asList(o1, o2, o3);

        BigDecimal total = service.total(orders);

        assertEquals(new BigDecimal("4000"), total);
    }

    @Test
    void total_allCancelled_returnsZero() {
        Order c1 = Order.builder().id(201L).customerName("lee").amount(new BigDecimal("100")).status(OrderStatus.CANCELLED).build();
        Order c2 = Order.builder().id(202L).customerName("lee").amount(new BigDecimal("200")).status(OrderStatus.CANCELLED).build();
        List<Order> orders = Arrays.asList(c1, c2);

        BigDecimal total = service.total(orders);

        assertEquals(BigDecimal.ZERO, total);
    }
}
