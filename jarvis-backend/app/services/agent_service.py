from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.schemas.chat import ChatResponse


class AgentService:
    """
    Facade maintaining compatibility with the ChatResponse schema while
    powering execution with the complete JARVIS AI Agent Brain.
    """

    def process_message(
        self,
        user_message: str,
        db: Session,
        conversation_id: Optional[int] = None,
        context_token: Optional[str] = None
    ) -> ChatResponse:
        from app.ai.agent import jarvis_agent
        result = jarvis_agent.process(
            db=db,
            message=user_message,
            conversation_id=conversation_id
        )

        plan_steps = [
            f"Step {s['step_number']}: {s.get('tool_name') or 'Reasoning'}"
            for s in result.get("plan", [])
        ]

        primary_tool = None
        if result.get("actions"):
            primary_tool = result["actions"][0].get("tool_name")

        return ChatResponse(
            message=result["response"],
            intent=result["intent"],
            plan=plan_steps,
            tool=primary_tool,
            status="completed" if result["agent_state"] != "ERROR" else "failed",
            verified=any(v.get("status") == "VERIFIED" for v in result.get("verification", [])),
            conversation_id=result.get("conversation_id"),
            context_token=context_token or "#CTX-78440",
            memory_accessed=None,
            details={
                "confidence": result["confidence"],
                "execution_time_ms": result["execution_time_ms"],
                "agent_state": result["agent_state"],
                "actions": result.get("actions", []),
                "verification": result.get("verification", [])
            }
        )


agent_service = AgentService()
