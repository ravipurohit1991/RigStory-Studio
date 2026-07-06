from fastapi import APIRouter

from app.api.routes import (
    characters,
    clips,
    health,
    jobs,
    motion,
    motion_plans,
    ollama,
    projects,
    scenes,
    settings,
)

api_router = APIRouter()
api_router.include_router(characters.router)
api_router.include_router(clips.router)
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(motion.router)
api_router.include_router(motion_plans.router)
api_router.include_router(ollama.router)
api_router.include_router(projects.router)
api_router.include_router(scenes.router)
api_router.include_router(settings.router)
