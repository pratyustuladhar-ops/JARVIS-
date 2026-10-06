from typing import Dict, Any
from sqlalchemy.orm import Session
from app.services.task_service import task_service
from app.services.project_service import project_service
from app.services.activity_service import activity_service
from app.services.cms_service import cms_service
from app.schemas.task import TaskResponse
from app.schemas.project import ProjectResponse


class DashboardService:
    def get_dashboard_data(self, db: Session) -> Dict[str, Any]:
        # Fetch dynamic tasks and projects from DB
        tasks = task_service.get_all(db, limit=5)
        projects = project_service.get_all(db, limit=5)
        activities = activity_service.get_recent(db, limit=6)

        # Pull dynamic values from CMS if configured, otherwise fallback to defaults
        greeting_header = cms_service.get_value(db, "dashboard.greeting", "Good morning, Commander.")
        greeting_sub = cms_service.get_value(
            db,
            "dashboard.subgreeting",
            "What can I help you accomplish? All autonomous computational subsystems stand synchronized."
        )
        quantum_state = cms_service.get_value(db, "system.quantum_state", "COHERENT 99.4%")
        entropy_val = cms_service.get_value(db, "system.entropy", "0.0028 Δ")
        insight_title = cms_service.get_value(
            db,
            "dashboard.insight.title",
            "Your Java practice has increased significantly this week."
        )
        insight_desc = cms_service.get_value(
            db,
            "dashboard.insight.description",
            "Autonomous heuristic tracking detected a 24% surge in codebase comprehension sessions. JARVIS suggests compiling a targeted concurrency revision module before tomorrow's scheduled sprint."
        )
        insight_trend = cms_service.get_value(db, "dashboard.insight.trend", "+24% activity trend")
        quick_actions = cms_service.get_value(
            db,
            "quick_actions.list",
            [
                {"title": "Start Focus Session", "subtitle": "POMODORO 45M", "icon": "filter_center_focus"},
                {"title": "Analyze File", "subtitle": "AST PARSE", "icon": "file_open"},
                {"title": "Open Project", "subtitle": "JAVA / DBMS", "icon": "folder_managed"},
                {"title": "Create Task", "subtitle": "NEW INTAKE", "icon": "add_task"},
                {"title": "Ask JARVIS", "subtitle": "NATURAL QUERY", "icon": "smart_toy"},
                {"title": "View Memory", "subtitle": "VECTOR GRAPH", "icon": "memory"}
            ]
        )

        return {
            "assistant_status": {
                "name": "JARVIS",
                "version": "OS // v4.2",
                "state": "READY // CORE SYNCHRONIZED",
                "status": "ONLINE",
                "throughput": "4.8 TB/s",
                "entropy": entropy_val,
                "quantum_state": quantum_state,
                "station_pos": "37.7749° N, 122.4194° W",
                "greeting": {
                    "header": greeting_header,
                    "subtext": greeting_sub
                }
            },
            "system_status": {
                "backend": "online",
                "database": "connected",
                "ai_core": "ONLINE",
                "voice": "READY",
                "memory": "CONNECTED",
                "tools": "12 AVAILABLE",
                "local_agent": "STANDBY (ACTIVE)",
                "database_status": "CONNECTED",
                "host": "JARVIS-NODE-01",
                "uptime": "142h 19m",
                "latency_ms": 12,
                "security_level": "L4 RESTRICTED"
            },
            "agent_pipeline": {
                "status": "PIPELINE: IDLE // READY FOR DISPATCH",
                "nodes": [
                    {"code": "01 // INTAKE", "name": "Intent", "status": "COMPLETED", "state": "done"},
                    {"code": "02 // SCHED", "name": "Plan", "status": "COMPLETED", "state": "done"},
                    {"code": "03 // BIND", "name": "Tool", "status": "STANDBY (12)", "state": "active"},
                    {"code": "04 // FORK", "name": "Execute", "status": "QUEUED", "state": "queued"},
                    {"code": "05 // AUDIT", "name": "Verify", "status": "AWAITING", "state": "awaiting"},
                    {"code": "06 // OUTPUT", "name": "Respond", "status": "AWAITING", "state": "awaiting"}
                ]
            },
            "active_tasks": [TaskResponse.model_validate(t).model_dump() for t in tasks],
            "projects": [ProjectResponse.model_validate(p).model_dump() for p in projects],
            "recent_activities": [
                {
                    "id": a.id,
                    "time": a.timestamp.strftime("%H:%M"),
                    "event_type": a.event_type,
                    "title": a.title,
                    "description": a.description,
                    "status": a.status
                }
                for a in activities
            ],
            "ai_insight": {
                "title": insight_title,
                "description": insight_desc,
                "trend": insight_trend,
                "metric": "REASONING_LOAD",
                "val": 84.2,
                "model": "COGNITION-LLM-4.2",
                "accuracy": "98.4%",
                "inference_status": "ACTIVE"
            },
            "quick_actions": quick_actions,
            "statistics": {
                "tasks_count": len(tasks),
                "projects_count": len(projects),
                "pipeline_workers": 8,
                "q_coherence": 0.994
            }
        }


dashboard_service = DashboardService()
