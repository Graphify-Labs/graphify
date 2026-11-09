#include <doctest/doctest.h>

static int add(int a, int b) { return a + b; }

TEST_CASE("addition works") {
    SUBCASE("small operands") {
        CHECK(add(1, 2) == 3);
    }
}

TEST_CASE("subtraction works") {
    CHECK(add(5, -1) == 4);
}

TEST_CASE("handles \"quoted\" names") {
    CHECK(add(0, 0) == 0);
}
