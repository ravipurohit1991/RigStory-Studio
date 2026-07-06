from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.math2d.aabb import Aabb
from app.domain.math2d.affine import Affine2
from app.domain.math2d.angles import (
    clamp,
    lerp_angle_deg,
    normalize_deg,
    shortest_delta_deg,
)
from app.domain.math2d.bezier import cubic_scalar, cubic_scalar_derivative
from app.domain.math2d.polygon import (
    centroid,
    contains_point,
    is_ccw,
    is_convex,
    signed_area,
)
from app.domain.math2d.transform import Transform2D
from app.domain.math2d.vec2 import Vec2

finite = st.floats(min_value=-100.0, max_value=100.0, allow_nan=False)
rotations = st.floats(min_value=-720.0, max_value=720.0, allow_nan=False)
scales = st.floats(min_value=0.1, max_value=10.0).flatmap(
    lambda magnitude: st.sampled_from([magnitude, -magnitude])
)


class TestVec2:
    def test_arithmetic(self) -> None:
        assert Vec2(1.0, 2.0) + Vec2(3.0, -1.0) == Vec2(4.0, 1.0)
        assert Vec2(1.0, 2.0) - Vec2(3.0, -1.0) == Vec2(-2.0, 3.0)
        assert -Vec2(1.0, -2.0) == Vec2(-1.0, 2.0)
        assert Vec2(1.0, 2.0).scaled(2.5) == Vec2(2.5, 5.0)

    def test_products_and_length(self) -> None:
        assert Vec2(1.0, 2.0).dot(Vec2(3.0, 4.0)) == pytest.approx(11.0)
        assert Vec2(1.0, 0.0).cross(Vec2(0.0, 1.0)) == pytest.approx(1.0)
        assert Vec2(3.0, 4.0).length() == pytest.approx(5.0)
        assert Vec2(3.0, 4.0).length_squared() == pytest.approx(25.0)
        assert Vec2(1.0, 1.0).distance_to(Vec2(4.0, 5.0)) == pytest.approx(5.0)

    def test_normalized(self) -> None:
        unit = Vec2(3.0, 4.0).normalized()
        assert unit.is_close(Vec2(0.6, 0.8))
        with pytest.raises(ValueError, match="zero-length"):
            Vec2(0.0, 0.0).normalized()

    def test_perpendicular_is_ccw(self) -> None:
        assert Vec2(1.0, 0.0).perpendicular() == Vec2(0.0, 1.0)
        assert Vec2(0.0, 1.0).perpendicular() == Vec2(-1.0, 0.0)

    def test_rotation_and_angle(self) -> None:
        rotated = Vec2(1.0, 0.0).rotated_deg(90.0)
        assert rotated.is_close(Vec2(0.0, 1.0))
        assert Vec2(0.0, -1.0).angle_deg() == pytest.approx(-90.0)

    def test_lerp(self) -> None:
        assert Vec2(0.0, 0.0).lerp(Vec2(10.0, -4.0), 0.25).is_close(Vec2(2.5, -1.0))


class TestAngles:
    def test_normalize_known_values(self) -> None:
        assert normalize_deg(0.0) == 0.0
        assert normalize_deg(180.0) == 180.0
        assert normalize_deg(-180.0) == 180.0
        assert normalize_deg(540.0) == 180.0
        assert normalize_deg(360.0) == 0.0
        assert normalize_deg(-90.0) == -90.0

    @given(rotations)
    def test_normalize_range_and_equivalence(self, degrees: float) -> None:
        wrapped = normalize_deg(degrees)
        assert -180.0 < wrapped <= 180.0
        difference = math.fmod(degrees - wrapped, 360.0)
        assert min(abs(difference), abs(abs(difference) - 360.0)) < 1e-9

    def test_shortest_delta(self) -> None:
        assert shortest_delta_deg(359.0, 1.0) == pytest.approx(2.0)
        assert shortest_delta_deg(1.0, 359.0) == pytest.approx(-2.0)
        assert shortest_delta_deg(-170.0, 170.0) == pytest.approx(-20.0)

    def test_lerp_through_zero(self) -> None:
        # 359 degrees to 1 degree must pass through 0, not 180.
        assert lerp_angle_deg(359.0, 1.0, 0.5) == pytest.approx(0.0)
        assert lerp_angle_deg(359.0, 1.0, 0.25) == pytest.approx(359.5 - 360.0)

    def test_clamp(self) -> None:
        assert clamp(5.0, 0.0, 1.0) == 1.0
        assert clamp(-5.0, 0.0, 1.0) == 0.0
        with pytest.raises(ValueError, match="inverted"):
            clamp(0.0, 1.0, -1.0)


class TestAffine2:
    def test_two_bone_composition_known_values(self) -> None:
        # bone_a: rotation 30 deg, length 10; bone_b at its tip, rotation 40 deg,
        # length 5. Endpoint = R30*(10,0) + R70*(5,0).
        bone_a = Affine2.from_trs(Vec2(0.0, 0.0), 30.0)
        bone_b = bone_a.multiply(Affine2.from_trs(Vec2(10.0, 0.0), 40.0))
        tip = bone_b.apply_point(Vec2(5.0, 0.0))
        assert tip.is_close(Vec2(10.370354754472732, 9.69846310392954), tolerance=1e-9)

    def test_inverse_known_values(self) -> None:
        transform = Affine2.from_trs(Vec2(3.0, -2.0), 90.0, (2.0, 1.0))
        point = Vec2(1.0, 1.0)
        image = transform.apply_point(point)
        assert image.is_close(Vec2(2.0, 0.0), tolerance=1e-9)
        assert transform.inverse().apply_point(image).is_close(point, tolerance=1e-9)

    def test_vector_transform_ignores_translation(self) -> None:
        transform = Affine2.from_trs(Vec2(100.0, 100.0), 90.0)
        assert transform.apply_vector(Vec2(1.0, 0.0)).is_close(Vec2(0.0, 1.0))

    def test_singular_matrix_rejected(self) -> None:
        singular = Affine2(1.0, 2.0, 2.0, 4.0, 0.0, 0.0)
        with pytest.raises(ValueError, match="singular"):
            singular.inverse()

    def test_rotation_decomposition(self) -> None:
        transform = Affine2.from_trs(Vec2(0.0, 0.0), 33.0)
        assert transform.rotation_deg() == pytest.approx(33.0)

    @given(tx=finite, ty=finite, rotation=rotations, sx=scales, sy=scales)
    def test_inverse_times_self_is_identity(
        self, tx: float, ty: float, rotation: float, sx: float, sy: float
    ) -> None:
        transform = Affine2.from_trs(Vec2(tx, ty), rotation, (sx, sy))
        product = transform.inverse().multiply(transform)
        assert product.is_close(Affine2.identity(), tolerance=1e-6)

    @given(tx=finite, ty=finite, rotation=rotations, sx=scales, sy=scales, px=finite, py=finite)
    def test_inverse_round_trips_points(
        self,
        tx: float,
        ty: float,
        rotation: float,
        sx: float,
        sy: float,
        px: float,
        py: float,
    ) -> None:
        transform = Affine2.from_trs(Vec2(tx, ty), rotation, (sx, sy))
        point = Vec2(px, py)
        restored = transform.inverse().apply_point(transform.apply_point(point))
        assert restored.is_close(point, tolerance=1e-4)

    @given(a=rotations, b=rotations, c=rotations)
    def test_composition_is_associative(self, a: float, b: float, c: float) -> None:
        ta = Affine2.from_trs(Vec2(1.0, 2.0), a)
        tb = Affine2.from_trs(Vec2(-3.0, 0.5), b)
        tc = Affine2.from_trs(Vec2(0.25, -8.0), c)
        left = ta.multiply(tb).multiply(tc)
        right = ta.multiply(tb.multiply(tc))
        assert left.is_close(right, tolerance=1e-9)


class TestTransform2D:
    def test_identity_defaults(self) -> None:
        transform = Transform2D.identity()
        assert transform.position == Vec2(0.0, 0.0)
        assert transform.rotation_deg == 0.0
        assert transform.scale == (1.0, 1.0)

    def test_compose_affine_matches_manual_composition(self) -> None:
        parent = Affine2.from_trs(Vec2(1.0, 1.0), 90.0)
        local = Transform2D(position=Vec2(2.0, 0.0), rotation_deg=0.0)
        world = local.compose_affine(parent)
        assert world.apply_point(Vec2(0.0, 0.0)).is_close(Vec2(1.0, 3.0), tolerance=1e-9)


class TestBezier:
    def test_endpoints_and_midpoint(self) -> None:
        assert cubic_scalar(0.0, 0.1, 0.9, 1.0, 0.0) == 0.0
        assert cubic_scalar(0.0, 0.1, 0.9, 1.0, 1.0) == 1.0
        assert cubic_scalar(0.0, 0.1, 0.9, 1.0, 0.5) == pytest.approx(0.5)

    def test_derivative(self) -> None:
        assert cubic_scalar_derivative(0.0, 0.1, 0.9, 1.0, 0.0) == pytest.approx(0.3)
        assert cubic_scalar_derivative(0.0, 0.1, 0.9, 1.0, 1.0) == pytest.approx(0.3)


class TestAabb:
    def test_from_points_and_queries(self) -> None:
        box = Aabb.from_points([Vec2(1.0, 5.0), Vec2(-2.0, 3.0), Vec2(0.0, 7.0)])
        assert box == Aabb(-2.0, 3.0, 1.0, 7.0)
        assert box.contains_point(Vec2(0.0, 5.0))
        assert not box.contains_point(Vec2(2.0, 5.0))
        assert box.center().is_close(Vec2(-0.5, 5.0))

    def test_union_and_intersects(self) -> None:
        a = Aabb(0.0, 0.0, 2.0, 2.0)
        b = Aabb(2.0, 1.0, 3.0, 3.0)
        c = Aabb(5.0, 5.0, 6.0, 6.0)
        assert a.intersects(b)  # touching edges count as intersecting
        assert not a.intersects(c)
        assert a.union(c) == Aabb(0.0, 0.0, 6.0, 6.0)

    def test_invalid_construction(self) -> None:
        with pytest.raises(ValueError, match="invalid AABB"):
            Aabb(1.0, 0.0, 0.0, 1.0)
        with pytest.raises(ValueError, match="zero points"):
            Aabb.from_points([])


SQUARE = [Vec2(0.0, 0.0), Vec2(1.0, 0.0), Vec2(1.0, 1.0), Vec2(0.0, 1.0)]
L_SHAPE = [
    Vec2(0.0, 0.0),
    Vec2(2.0, 0.0),
    Vec2(2.0, 1.0),
    Vec2(1.0, 1.0),
    Vec2(1.0, 2.0),
    Vec2(0.0, 2.0),
]


class TestPolygon:
    def test_signed_area_and_winding(self) -> None:
        assert signed_area(SQUARE) == pytest.approx(1.0)
        assert signed_area(list(reversed(SQUARE))) == pytest.approx(-1.0)
        assert is_ccw(SQUARE)

    def test_centroid(self) -> None:
        assert centroid(SQUARE).is_close(Vec2(0.5, 0.5))

    def test_convexity(self) -> None:
        assert is_convex(SQUARE)
        assert not is_convex(L_SHAPE)

    def test_contains_point(self) -> None:
        assert contains_point(SQUARE, Vec2(0.5, 0.5))
        assert not contains_point(SQUARE, Vec2(1.5, 0.5))
        assert contains_point(L_SHAPE, Vec2(0.5, 1.5))
        assert not contains_point(L_SHAPE, Vec2(1.5, 1.5))

    def test_degenerate_rejected(self) -> None:
        with pytest.raises(ValueError, match="three vertices"):
            signed_area([Vec2(0.0, 0.0), Vec2(1.0, 0.0)])
