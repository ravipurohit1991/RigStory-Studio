from __future__ import annotations

import pytest

from app.domain.common import TransformSpec
from app.domain.errors import DomainValidationError
from app.domain.rig import (
    BoneDefinition,
    JointLimit,
    RigDefinition,
    compute_bone_endpoints,
    compute_world_transforms,
    validate_rig,
)
from tests.sample_paths import load_sample

MIRRORED_BONES = (
    "eye",
    "clavicle",
    "upper_arm",
    "forearm",
    "hand",
    "thigh",
    "shin",
    "foot",
)


def _codes(rig: RigDefinition) -> set[str]:
    return {issue.code for issue in validate_rig(rig)}


def _bone(bone_id: str, parent: str | None = None, length: float = 1.0) -> BoneDefinition:
    return BoneDefinition(id=bone_id, parent_id=parent, length=length)


class TestValidation:
    def test_two_bone_fixture_is_valid(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-two-bone.json"))
        assert validate_rig(rig) == []

    def test_biped_fixture_is_valid(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-canonical-biped.json"))
        assert validate_rig(rig) == []
        assert len(rig.bones) == 25

    def test_cycle_fixture(self) -> None:
        rig = RigDefinition.model_validate(load_sample("invalid/rig-cycle.json"))
        assert "RIG_CYCLE" in _codes(rig)

    def test_duplicate_id_fixture(self) -> None:
        rig = RigDefinition.model_validate(load_sample("invalid/rig-duplicate-bone-id.json"))
        assert "RIG_DUPLICATE_BONE_ID" in _codes(rig)

    def test_missing_parent_fixture_is_also_disconnected(self) -> None:
        rig = RigDefinition.model_validate(load_sample("invalid/rig-missing-parent.json"))
        codes = _codes(rig)
        assert "RIG_MISSING_PARENT" in codes
        assert "RIG_DISCONNECTED_BONE" in codes

    def test_multiple_roots(self) -> None:
        rig = RigDefinition(id="rig_test", name="t", bones=(_bone("a"), _bone("b")))
        assert "RIG_MULTIPLE_ROOTS" in _codes(rig)

    def test_no_root(self) -> None:
        rig = RigDefinition(id="rig_test", name="t", bones=(_bone("a", "b"), _bone("b", "a")))
        codes = _codes(rig)
        assert "RIG_NO_ROOT" in codes
        assert "RIG_CYCLE" in codes

    def test_self_parent(self) -> None:
        rig = RigDefinition(id="rig_test", name="t", bones=(_bone("a"), _bone("b", "b")))
        assert "RIG_SELF_PARENT" in _codes(rig)

    def test_no_bones(self) -> None:
        rig = RigDefinition(id="rig_test", name="t", bones=())
        assert "RIG_NO_BONES" in _codes(rig)

    def test_issue_paths_point_at_offending_bone(self) -> None:
        rig = RigDefinition(id="rig_test", name="t", bones=(_bone("a"), _bone("b", "ghost")))
        issues = [issue for issue in validate_rig(rig) if issue.code == "RIG_MISSING_PARENT"]
        assert issues[0].path == "bones[1].parent_id"

    def test_inverted_joint_limit_rejected_at_parse_time(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            JointLimit(min_rotation_deg=10.0, max_rotation_deg=-10.0)


class TestForwardKinematics:
    def test_two_bone_known_endpoint(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-two-bone.json"))
        endpoints = compute_bone_endpoints(rig)
        origin_b, tip_b = endpoints["bone_b"]
        assert origin_b.x == pytest.approx(8.660254037844387, abs=1e-12)
        assert origin_b.y == pytest.approx(5.0, abs=1e-12)
        assert tip_b.x == pytest.approx(10.370354754472732, abs=1e-12)
        assert tip_b.y == pytest.approx(9.69846310392954, abs=1e-12)

    def test_child_inherits_parent_transform(self) -> None:
        rig = RigDefinition(
            id="rig_test",
            name="t",
            bones=(
                BoneDefinition(
                    id="a",
                    setup_transform=TransformSpec(position=(1.0, 1.0), rotation_deg=90.0),
                    length=2.0,
                ),
                BoneDefinition(
                    id="b",
                    parent_id="a",
                    setup_transform=TransformSpec(position=(2.0, 0.0)),
                    length=1.0,
                ),
            ),
        )
        endpoints = compute_bone_endpoints(rig)
        origin_b, tip_b = endpoints["b"]
        assert origin_b.x == pytest.approx(1.0, abs=1e-12)
        assert origin_b.y == pytest.approx(3.0, abs=1e-12)
        assert tip_b.x == pytest.approx(1.0, abs=1e-12)
        assert tip_b.y == pytest.approx(4.0, abs=1e-12)

    def test_biped_endpoints_match_goldens(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-canonical-biped.json"))
        endpoints = compute_bone_endpoints(rig)
        golden = load_sample("fixtures/math-golden.json")
        endpoint_section = golden["bone_endpoints"]
        assert isinstance(endpoint_section, dict)
        biped_goldens = endpoint_section["rig-canonical-biped.json"]
        assert isinstance(biped_goldens, dict)
        for bone_id, expected in biped_goldens.items():
            assert isinstance(expected, dict)
            origin, tip = endpoints[bone_id]
            expected_origin = expected["origin"]
            expected_tip = expected["tip"]
            assert isinstance(expected_origin, list)
            assert isinstance(expected_tip, list)
            assert origin.x == pytest.approx(expected_origin[0], abs=1e-12)
            assert origin.y == pytest.approx(expected_origin[1], abs=1e-12)
            assert tip.x == pytest.approx(expected_tip[0], abs=1e-12)
            assert tip.y == pytest.approx(expected_tip[1], abs=1e-12)

    def test_biped_bilateral_symmetry(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-canonical-biped.json"))
        endpoints = compute_bone_endpoints(rig)
        for stem in MIRRORED_BONES:
            left_origin, _ = endpoints[f"{stem}_l"]
            right_origin, _ = endpoints[f"{stem}_r"]
            assert left_origin.x == pytest.approx(-right_origin.x, abs=1e-9), stem
            assert left_origin.y == pytest.approx(right_origin.y, abs=1e-9), stem

    def test_biped_feet_rest_on_ground(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-canonical-biped.json"))
        endpoints = compute_bone_endpoints(rig)
        for bone_id in ("toe_l", "toe_r"):
            _, tip = endpoints[bone_id]
            assert 0.0 <= tip.y <= 0.1, bone_id

    def test_invalid_rig_rejected(self) -> None:
        rig = RigDefinition.model_validate(load_sample("invalid/rig-cycle.json"))
        with pytest.raises(DomainValidationError):
            compute_world_transforms(rig)

    def test_deterministic_repeat_evaluation(self) -> None:
        rig = RigDefinition.model_validate(load_sample("fixtures/rig-canonical-biped.json"))
        first = compute_bone_endpoints(rig)
        second = compute_bone_endpoints(rig)
        assert first == second
