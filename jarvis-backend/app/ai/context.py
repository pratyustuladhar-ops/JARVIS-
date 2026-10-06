import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.models.task import Task
from app.models.project import Project
from app.models.memory import Memory
from app.models.chat import Message, Conversation
from app.services.settings_service import settings_service

logger = logging.getLogger("jarvis.ai.context")


class AgentContext(BaseModel):
    user_message: str
    intent: str
    recent_messages: List[Dict[str, str]] = []
    relevant_tasks: List[Dict[str, Any]] = []
    relevant_projects: List[Dict[str, Any]] = []
    relevant_memories: List[Dict[str, Any]] = []
    system_settings: Dict[str, Any] = {}
    last_action_context: Optional[Dict[str, Any]] = None
    visual_context: Optional[Dict[str, Any]] = None
    input_type: str = "text"


class ContextManager:
    """
    Selective Context Retrieval Engine:
    Gathers only targeted, relevant state without flooding the prompt or querying full tables.
    """

    def gather_context(
        self,
        db: Session,
        user_message: str,
        intent: str,
        conversation_id: Optional[int] = None,
        visual_context: Optional[Dict[str, Any]] = None,
        input_type: str = "text"
    ) -> AgentContext:
        msg_lower = user_message.lower()

        # 1. Recent conversation messages (selective last 4 turns)
        recent_msgs = []
        if conversation_id:
            db_msgs = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc())
                .limit(4)
                .all()
            )
            for m in reversed(db_msgs):
                recent_msgs.append({"role": m.role, "content": m.content})

        # 2. Targeted Task Retrieval
        relevant_tasks = []
        if "TASK" in intent or any(k in msg_lower for k in ["task", "todo", "due", "assignment"]):
            task_query = db.query(Task)
            # If a specific word is mentioned, filter; otherwise return active tasks
            words = [w for w in msg_lower.split() if len(w) > 3 and w not in ["task", "create", "what", "have", "today"]]
            if words:
                conditions = [Task.title.ilike(f"%{w}%") for w in words]
                tasks = task_query.filter(*conditions).limit(5).all()
            else:
                tasks = task_query.order_by(Task.updated_at.desc()).limit(5).all()

            for t in tasks:
                relevant_tasks.append({
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "progress": t.progress
                })

        # 3. Targeted Project Retrieval
        relevant_projects = []
        if "PROJECT" in intent or any(k in msg_lower for k in ["project", "repo", "java", "dbms"]):
            proj_query = db.query(Project)
            words = [w for w in msg_lower.split() if len(w) > 3 and w not in ["project", "create", "what", "show"]]
            if words:
                conditions = [Project.name.ilike(f"%{w}%") for w in words]
                projects = proj_query.filter(*conditions).limit(3).all()
            else:
                projects = proj_query.order_by(Project.updated_at.desc()).limit(3).all()

            for p in projects:
                relevant_projects.append({
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "progress": p.progress
                })

        # 4. Targeted Memory Retrieval
        relevant_memories = []
        mem_query = db.query(Memory)
        search_terms = [w for w in msg_lower.split() if len(w) > 3]
        if search_terms:
            for m in mem_query.all():
                if any(term in m.content.lower() for term in search_terms):
                    relevant_memories.append({
                        "id": m.id,
                        "content": m.content,
                        "memory_type": m.memory_type,
                        "importance": m.importance
                    })
                    if len(relevant_memories) >= 3:
                        break

        # 5. System Settings Snapshot
        sys_settings = settings_service.get_settings(db)
        settings_snapshot = {
            "assistant_name": sys_settings.assistant_name,
            "operator_callsign": sys_settings.operator_callsign,
            "persistent_memory": sys_settings.persistent_memory,
            "reasoning_depth": sys_settings.reasoning_depth
        }

        return AgentContext(
            user_message=user_message,
            intent=intent,
            recent_messages=recent_msgs,
            relevant_tasks=relevant_tasks,
            relevant_projects=relevant_projects,
            relevant_memories=relevant_memories,
            system_settings=settings_snapshot,
            visual_context=visual_context,
            input_type=input_type
        )


context_manager = ContextManager()
