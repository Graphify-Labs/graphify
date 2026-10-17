package com.example.shop;

public class Product {
    private final String name;
    private final int priceCents;

    public Product(String name, int priceCents) {
        this.name = name;
        this.priceCents = priceCents;
    }

    public String getName() {
        return name;
    }

    public int getPriceCents() {
        return priceCents;
    }
}
