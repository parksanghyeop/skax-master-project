package com.example.demo.customer;

/** 고객 정보 — 값만 담는 객체(엔티티 아님). 할인 계산의 입력으로 쓰인다. */
public class Customer {

    private final String name;
    private final Grade grade;

    public Customer(String name, Grade grade) {
        this.name = name;
        this.grade = grade;
    }

    public String getName() {
        return name;
    }

    public Grade getGrade() {
        return grade;
    }
}
