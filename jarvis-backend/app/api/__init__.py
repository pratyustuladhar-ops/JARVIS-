from fastapi import APIRouter
from app.api.dashboard import router as dashboard_router
from app.api.assistant import router as assistant_router
from app.api.tasks import router as tasks_router
from app.api.memory import router as memory_router
from app.api.projects import router as projects_router
from app.api.activity import router as activity_router
from app.api.cms import router as cms_router
from app.api.settings import router as settings_router
from app.api.settings import get_system_status
from app.api.local_agent import router as local_agent_router
from app.api.voice import router as voice_router

system_router = APIRouter()
system_router.add_api_route("/status", get_system_status, methods=["GET"], summary="Get verified system status")

api_router = APIRouter()

api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(assistant_router, prefix="/assistant", tags=["Assistant"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(memory_router, prefix="/memory", tags=["Memory"])
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(activity_router, prefix="/activity", tags=["Activity"])
api_router.include_router(cms_router, prefix="/cms", tags=["CMS & Admin Config"])
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])
api_router.include_router(local_agent_router, prefix="/local-agent", tags=["Windows Local Agent"])
api_router.include_router(voice_router, prefix="/voice", tags=["Voice & Wake Word"])
api_router.include_router(system_router, prefix="/system", tags=["System Status"])


