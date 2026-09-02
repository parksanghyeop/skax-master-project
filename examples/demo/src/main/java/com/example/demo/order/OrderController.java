package com.example.demo.order;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 주문 CRUD REST API. 판단 로직은 전부 OrderService에 있다. */
@RestController
@RequestMapping("/orders")
public class OrderController {

    public record CreateOrderRequest(String customerName, BigDecimal amount) {}

    public record UpdateAmountRequest(BigDecimal amount) {}

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Order create(@RequestBody CreateOrderRequest request) {
        return service.create(request.customerName(), request.amount());
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) {
        return service.findById(id);
    }

    @GetMapping
    public List<Order> list() {
        return service.findAll();
    }

    @PutMapping("/{id}/amount")
    public Order updateAmount(@PathVariable Long id, @RequestBody UpdateAmountRequest request) {
        return service.updateAmount(id, request.amount());
    }

    @PostMapping("/{id}/pay")
    public Order pay(@PathVariable Long id) {
        return service.pay(id);
    }

    @PostMapping("/{id}/cancel")
    public Order cancel(@PathVariable Long id) {
        return service.cancel(id);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        service.delete(id);
    }
}
