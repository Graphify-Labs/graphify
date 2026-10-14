package com.example.shop;

import java.util.ArrayList;
import java.util.List;

public class OrderService {
    private final List<Product> items = new ArrayList<>();

    public void add(Product product) {
        items.add(product);
    }

    public List<Product> listItems() {
        return items;
    }
}
