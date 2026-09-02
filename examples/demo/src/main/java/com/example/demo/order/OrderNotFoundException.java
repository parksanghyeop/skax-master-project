package com.example.demo.order;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/** 존재하지 않는 주문 id를 조회·수정·삭제할 때 던진다 (HTTP 404). */
@ResponseStatus(HttpStatus.NOT_FOUND)
public class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(Long id) {
        super("order not found: " + id);
    }
}
