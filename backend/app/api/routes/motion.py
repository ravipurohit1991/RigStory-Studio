from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_project_store
from app.domain.motion import compile_motion_actions
from app.schemas.motion import MotionCompileRead, MotionCompileRequest
from app.services.project_store import FileProjectStore, ProjectNotFoundError

router = APIRouter(prefix="/motion/demo", tags=["motion"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]


@router.post("/compile", response_model=MotionCompileRead)
def compile_demo_motion(
    payload: MotionCompileRequest,
    store: ProjectStoreDep,
) -> MotionCompileRead:
    try:
        stored_scene = store.get_scene(payload.scene_id)
        project = store.get_project(stored_scene.project_id).document
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc

    character = next(
        (candidate for candidate in project.characters if candidate.id == payload.character_id),
        None,
    )
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    if not any(actor.id == payload.actor_id for actor in stored_scene.scene.actors):
        raise HTTPException(status_code=404, detail="actor not found")

    result = compile_motion_actions(
        scene=stored_scene.scene,
        actor_id=payload.actor_id,
        character=character,
        actions=payload.actions,
        clip_id=payload.clip_id,
        clip_name=payload.clip_name,
        style=payload.style,
    )
    return MotionCompileRead.model_validate(result.model_dump(mode="json"))
