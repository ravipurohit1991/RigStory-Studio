from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import (
    get_job_runner,
    get_motion_plan_compile_service,
    get_motion_plan_service,
)
from app.application.jobs import InlineJobRunner
from app.application.motion.compile import MotionPlanCompileService
from app.application.motion.planner import MotionPlanService
from app.domain.motion_plan import (
    CANNED_MOTION_PLAN_DRAFT,
    MotionPlanPatch,
    PatchSetParameters,
)
from app.infrastructure.llm.mock import ScriptedLLMProvider, content_result, model_result
from app.infrastructure.llm.prompt_registry import PromptRegistry
from app.main import app
from app.schemas.motion_plans import MAX_PROMPT_TEXT_LENGTH
from app.services.project_store import FileProjectStore
from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def _install(tmp_path: Path, provider: ScriptedLLMProvider) -> None:
    store = FileProjectStore(tmp_path)
    runner = InlineJobRunner()
    app.dependency_overrides[get_job_runner] = lambda: runner
    app.dependency_overrides[get_motion_plan_service] = lambda: MotionPlanService(
        provider=provider, prompt_registry=PromptRegistry(), store=store
    )
    app.dependency_overrides[get_motion_plan_compile_service] = lambda: MotionPlanCompileService(
        store=store
    )


def _create_project_with_scene(client: TestClient) -> tuple[str, str]:
    created = client.post(
        "/api/v1/projects", json={"document": load_sample("projects/biped-demo.rigstory.json")}
    ).json()
    project_id = created["document"]["project"]["id"]
    added = client.post(
        f"/api/v1/projects/{project_id}/scenes",
        json={
            "scene": room_scene()
            .model_copy(update={"id": "scene_plan_room"})
            .model_dump(mode="json"),
            "expected_revision": created["revision"],
        },
    )
    assert added.status_code == 201
    return project_id, added.json()["revision"]


def test_generate_plan_end_to_end(client: TestClient, tmp_path: Path) -> None:
    project_id, revision = _create_project_with_scene(client)
    _install(tmp_path, ScriptedLLMProvider([model_result(CANNED_MOTION_PLAN_DRAFT)]))

    response = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": "Mira walks to the chair, sits down, and waves.",
            "expected_revision": revision,
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert job["state"] == "succeeded"
    result = job["result"]
    assert result["status"] == "succeeded"
    plan_id = result["plan_id"]
    assert plan_id.startswith("plan_")
    assert [action["type"] for action in result["plan"]["actions"]] == [
        "locomote",
        "sit",
        "wave",
    ]

    fetched = client.get(f"/api/v1/motion-plans/{plan_id}")
    assert fetched.status_code == 200
    assert fetched.json()["plan"]["prompt"].startswith("Mira walks")

    project = client.get(f"/api/v1/projects/{project_id}").json()
    assert len(project["document"]["motion_plans"]) == 1
    records = project["document"]["generation_records"]
    assert len(records) == 1
    assert records[0]["kind"] == "motion_plan"
    assert records[0]["plan_id"] == plan_id


def test_unknown_target_is_rejected_not_fabricated(client: TestClient, tmp_path: Path) -> None:
    _, revision = _create_project_with_scene(client)
    bad_draft = CANNED_MOTION_PLAN_DRAFT.model_copy(
        update={
            "actions": tuple(
                action.model_copy(update={"target_ref": "sofa_1.seat"})
                if action.type == "sit"
                else action
                for action in CANNED_MOTION_PLAN_DRAFT.actions
            )
        }
    )
    # Both the initial and the repair response reference the unknown target.
    _install(tmp_path, ScriptedLLMProvider([model_result(bad_draft), model_result(bad_draft)]))

    response = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={"model": "planner", "prompt": "sit on the sofa", "expected_revision": revision},
    )
    job = response.json()
    assert job["state"] == "failed"
    assert job["error_kind"] == "invalid_response"
    attempts = job["error_detail"]["attempts"]
    assert any(
        "PLAN_UNKNOWN_TARGET" in error for attempt in attempts for error in attempt["error_summary"]
    )


def test_malformed_plan_repaired_once_then_fails_cleanly(
    client: TestClient, tmp_path: Path
) -> None:
    project_id, revision = _create_project_with_scene(client)
    _install(
        tmp_path,
        ScriptedLLMProvider([content_result("not json"), model_result(CANNED_MOTION_PLAN_DRAFT)]),
    )
    repaired = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={"model": "planner", "prompt": "walk and wave", "expected_revision": revision},
    ).json()
    assert repaired["state"] == "succeeded"
    assert repaired["result"]["status"] == "repaired"

    revision = repaired["result"]["revision"]
    _install(tmp_path, ScriptedLLMProvider([content_result("bad"), content_result("also bad")]))
    failed = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={"model": "planner", "prompt": "walk and wave", "expected_revision": revision},
    ).json()
    assert failed["state"] == "failed"
    assert failed["error_kind"] == "invalid_response"
    # The failed generation left the project unchanged.
    project = client.get(f"/api/v1/projects/{project_id}").json()
    assert project["revision"] == revision


def test_generate_plan_rejects_oversized_prompt_before_job_starts(
    client: TestClient, tmp_path: Path
) -> None:
    _, revision = _create_project_with_scene(client)
    provider = ScriptedLLMProvider([model_result(CANNED_MOTION_PLAN_DRAFT)])
    _install(tmp_path, provider)

    response = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": "x" * (MAX_PROMPT_TEXT_LENGTH + 1),
            "expected_revision": revision,
        },
    )

    assert response.status_code == 422
    assert provider.calls == []


def test_compile_links_clip_to_plan_and_recompiles_stably(
    client: TestClient, tmp_path: Path
) -> None:
    project_id, revision = _create_project_with_scene(client)
    _install(tmp_path, ScriptedLLMProvider([]))

    generated = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": "walk, sit, wave",
            "expected_revision": revision,
            "use_fixture": True,
        },
    ).json()
    assert generated["state"] == "succeeded"
    plan_id = generated["result"]["plan_id"]
    revision = generated["result"]["revision"]

    compiled = client.post(
        f"/api/v1/motion-plans/{plan_id}/compile",
        json={"expected_revision": revision, "clip_name": "Walk sit wave"},
    ).json()
    assert compiled["state"] == "succeeded"
    clip_id = compiled["result"]["clip_id"]
    revision = compiled["result"]["revision"]
    assert compiled["result"]["report"]["metrics"]["max_joint_limit_violation_deg"] == 0.0

    project = client.get(f"/api/v1/projects/{project_id}").json()
    clips = project["document"]["clips"]
    stored_clip = next(clip for clip in clips if clip["id"] == clip_id)
    assert stored_clip["source_plan_id"] == plan_id
    assert stored_clip["engine_version"] == compiled["result"]["engine_version"]

    # Edit the plan (user-editable before/after compile), then recompile: the
    # clip id stays stable and the clip content is replaced.
    plan = client.get(f"/api/v1/motion-plans/{plan_id}").json()["plan"]
    plan["actions"] = [
        {**action, "duration": 2.0} if action["id"] == "a3" else action
        for action in plan["actions"]
    ]
    updated = client.patch(
        f"/api/v1/motion-plans/{plan_id}",
        json={"plan": plan, "expected_revision": revision},
    )
    assert updated.status_code == 200
    revision = updated.json()["revision"]

    recompiled = client.post(
        f"/api/v1/motion-plans/{plan_id}/compile",
        json={"expected_revision": revision, "clip_name": "Walk sit wave"},
    ).json()
    assert recompiled["state"] == "succeeded"
    assert recompiled["result"]["clip_id"] == clip_id
    project = client.get(f"/api/v1/projects/{project_id}").json()
    assert len([c for c in project["document"]["clips"] if c["id"] == clip_id]) == 1


def test_correction_patch_preview_apply_and_undo(client: TestClient, tmp_path: Path) -> None:
    _, revision = _create_project_with_scene(client)
    patch = MotionPlanPatch(
        summary="make the wave smaller",
        operations=(PatchSetParameters(action_id="a3", amplitude=0.2),),
    )
    provider = ScriptedLLMProvider([model_result(patch)])
    _install(tmp_path, provider)

    generated = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": "walk, sit, wave",
            "expected_revision": revision,
            "use_fixture": True,
        },
    ).json()
    plan_id = generated["result"]["plan_id"]
    revision = generated["result"]["revision"]
    original_plan = client.get(f"/api/v1/motion-plans/{plan_id}").json()["plan"]

    preview = client.post(
        f"/api/v1/motion-plans/{plan_id}/patch",
        json={
            "model": "planner",
            "instruction": "Keep her left foot planted and make the wave smaller.",
            "action_ids": ["a3"],
            "expected_revision": revision,
        },
    ).json()
    assert preview["state"] == "succeeded"
    result = preview["result"]
    assert result["diff"] == ["set amplitude=0.2 on action a3"]
    patched_wave = next(
        action for action in result["patched_plan"]["actions"] if action["id"] == "a3"
    )
    assert patched_wave["amplitude"] == 0.2
    revision = result["revision"]

    # The patch is not applied yet: the stored plan is unchanged.
    stored = client.get(f"/api/v1/motion-plans/{plan_id}").json()["plan"]
    assert stored == original_plan

    applied = client.post(
        f"/api/v1/motion-plans/{plan_id}/apply-patch",
        json={"patch": result["patch"], "expected_revision": revision},
    )
    assert applied.status_code == 200
    applied_body = applied.json()
    assert applied_body["previous_plan"] == original_plan
    stored = client.get(f"/api/v1/motion-plans/{plan_id}").json()["plan"]
    assert next(a for a in stored["actions"] if a["id"] == "a3")["amplitude"] == 0.2
    # Only the intended action changed.
    assert [a for a in stored["actions"] if a["id"] != "a3"] == [
        a for a in original_plan["actions"] if a["id"] != "a3"
    ]

    # Undo: re-save the previous plan through the ordinary edit endpoint.
    undone = client.patch(
        f"/api/v1/motion-plans/{plan_id}",
        json={
            "plan": applied_body["previous_plan"],
            "expected_revision": applied_body["document_revision"],
        },
    )
    assert undone.status_code == 200
    stored = client.get(f"/api/v1/motion-plans/{plan_id}").json()["plan"]
    assert stored == original_plan

    # The patch audit record was committed.
    records = client.get(f"/api/v1/projects/{undone.json()['document']['project']['id']}")
    kinds = [record["kind"] for record in records.json()["document"]["generation_records"]]
    assert "motion_plan_patch" in kinds


def test_plan_validate_route_reports_errors(client: TestClient, tmp_path: Path) -> None:
    _, revision = _create_project_with_scene(client)
    _install(tmp_path, ScriptedLLMProvider([]))
    generated = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": "walk, sit, wave",
            "expected_revision": revision,
            "use_fixture": True,
        },
    ).json()
    plan_id = generated["result"]["plan_id"]
    validation = client.post(f"/api/v1/motion-plans/{plan_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["errors"] == []


def test_handshake_fixture_plans_and_compiles_two_actors(
    client: TestClient, tmp_path: Path
) -> None:
    project_id, revision = _create_project_with_scene(client)
    _install(tmp_path, ScriptedLLMProvider([]))

    generated = client.post(
        "/api/v1/scenes/scene_plan_room/motion-plans/generate",
        json={
            "model": "planner",
            "prompt": (
                "Mira approaches Jon, shakes his right hand, then they both look toward the door."
            ),
            "expected_revision": revision,
            "use_fixture": True,
        },
    ).json()
    assert generated["state"] == "succeeded"
    plan = generated["result"]["plan"]
    assert any(action["type"] == "handshake" for action in plan["actions"])
    assert len({action["actor_id"] for action in plan["actions"]}) == 2
    assert plan["contacts"][0]["kind"] == "hand_to_hand"

    compiled = client.post(
        f"/api/v1/motion-plans/{generated['result']['plan_id']}/compile",
        json={
            "expected_revision": generated["result"]["revision"],
            "clip_name": "Handshake",
        },
    ).json()
    assert compiled["state"] == "succeeded"
    report = compiled["result"]["report"]
    assert report["metrics"]["penetration_frames"] == 0

    project = client.get(f"/api/v1/projects/{project_id}").json()
    clip = next(
        clip for clip in project["document"]["clips"] if clip["id"] == compiled["result"]["clip_id"]
    )
    marker_kinds = {marker["kind"] for marker in clip["markers"]}
    assert {"contact", "sync"} <= marker_kinds


def test_unknown_plan_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/motion-plans/plan_missing").status_code == 404
