import 'package:flutter/material.dart';

class Greeter {
  final String name;

  Greeter(this.name);

  String greet() {
    return helper();
  }

  String helper() {
    return 'hello $name';
  }
}

int add(int a, int b) => a + b;

void runGreeter() {
  final g = Greeter('world');
  g.greet();
  add(1, 2);
}
