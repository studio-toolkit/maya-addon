"""Small pure-Python math helpers for UV tools."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> "Vec2":
        return Vec2(self.x / scalar, self.y / scalar)

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def rotated(self, angle: float, origin: "Vec2" | None = None) -> "Vec2":
        origin = origin or Vec2()
        local = self - origin
        sin_a = math.sin(angle)
        cos_a = math.cos(angle)
        return Vec2(
            local.x * cos_a - local.y * sin_a + origin.x,
            local.x * sin_a + local.y * cos_a + origin.y,
        )

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __truediv__(self, scalar: float) -> "Vec3":
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def axis_value(self, axis: str) -> float:
        return {"X": self.x, "Y": self.y, "Z": self.z}[axis]


@dataclass
class Bounds2D:
    min_x: float = float("inf")
    min_y: float = float("inf")
    max_x: float = float("-inf")
    max_y: float = float("-inf")

    def include(self, point: Vec2) -> None:
        self.min_x = min(self.min_x, point.x)
        self.min_y = min(self.min_y, point.y)
        self.max_x = max(self.max_x, point.x)
        self.max_y = max(self.max_y, point.y)

    def include_many(self, points: list[Vec2]) -> None:
        for point in points:
            self.include(point)

    @property
    def is_valid(self) -> bool:
        return self.min_x != float("inf") and self.max_x != float("-inf")

    @property
    def width(self) -> float:
        return 0.0 if not self.is_valid else self.max_x - self.min_x

    @property
    def height(self) -> float:
        return 0.0 if not self.is_valid else self.max_y - self.min_y

    @property
    def center(self) -> Vec2:
        if not self.is_valid:
            return Vec2()
        return Vec2((self.min_x + self.max_x) * 0.5, (self.min_y + self.max_y) * 0.5)


def polygon_area(points: list[Vec2]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i, point in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        total += point.x * nxt.y - nxt.x * point.y
    return total * 0.5

