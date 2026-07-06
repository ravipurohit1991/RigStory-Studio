from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.motion import MotionAction, MotionCompileResult, MotionStyle


class MotionCompileRequest(BaseModel):
    scene_id: str
    actor_id: str
    character_id: str
    clip_id: str = "clip_demo_motion"
    clip_name: str = "Developer motion"
    actions: tuple[MotionAction, ...]
    style: MotionStyle = MotionStyle()

    model_config = ConfigDict(frozen=True)


class MotionCompileRead(MotionCompileResult):
    pass
