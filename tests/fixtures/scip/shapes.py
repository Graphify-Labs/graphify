"""Source of tests/fixtures/scip/shapes.scip (see tests/test_scip_index.py)."""


class Shape:
    def area(self) -> float:
        return 0.0


class Square(Shape):
    def __init__(self, side: float) -> None:
        self.side = side

    def area(self) -> float:
        return self.side * self.side


def total(shapes: list[Shape]) -> float:
    return sum(s.area() for s in shapes)
