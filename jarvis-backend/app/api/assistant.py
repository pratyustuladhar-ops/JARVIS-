from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ConversationResponse
from app.schemas.agent import AgentMessageRequest, AgentMessageResponse, MultimodalMessageRequest
from app.services.assistant_service import assistant_service
from app.ai.agent import jarvis_agent
from app.ai.tools import agent_tool_registry
from app.tools.system_tool import SystemInfoTool
from app.core.config import settings

router = APIRouter()


@router.post("/message", response_model=AgentMessageResponse, summary="Send message through the JARVIS AI Agent Brain")
def send_agent_message(req: AgentMessageRequest, db: Session = Depends(get_db)):
    """
    Primary endpoint for the full 8-stage JARVIS AI reasoning pipeline:
    Input -> Intent Detection -> Context Retrieval -> Planner -> Tool Execution -> Verification -> Memory -> Response
    """
    clean_msg = req.message.strip() if req.message else ""
    if not clean_msg and not req.image_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be blank."
        )

    result = jarvis_agent.process(
        db=db,
        message=clean_msg,
        conversation_id=req.conversation_id,
        input_type=req.input_type,
        image_data=req.image_data,
        image_metadata=req.image_metadata
    )
    return result


@router.post("/multimodal", response_model=AgentMessageResponse, summary="Send Multimodal Message (Text, Voice, Image, Screen)")
def send_multimodal_message(req: MultimodalMessageRequest, db: Session = Depends(get_db)):
    """
    Dedicated endpoint for multimodal requests supporting attached images, screenshots, and visual reasoning.
    Reuses the full 8-stage JARVIS AI reasoning pipeline.
    """
    raw_text = req.message or req.content or ""
    clean_msg = raw_text.strip()
    if not clean_msg and not req.image_data:
        clean_msg = "What is on my screen?"

    # Validation: Check image format and size boundaries
    if req.image_data:
        raw_b64 = req.image_data.split(",")[-1] if "," in req.image_data else req.image_data
        approx_size_bytes = (len(raw_b64) * 3) / 4
        max_bytes = getattr(settings, "MAX_IMAGE_SIZE_MB", 10) * 1024 * 1024
        if approx_size_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image size exceeds maximum threshold of {settings.MAX_IMAGE_SIZE_MB}MB."
            )

        if req.image_data.startswith("data:") and not req.image_data.startswith("data:image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported media format. Only image files (PNG, JPEG, WebP) are accepted."
            )

    result = jarvis_agent.process(
        db=db,
        message=clean_msg,
        conversation_id=req.conversation_id,
        input_type=req.input_type,
        image_data=req.image_data,
        image_metadata=req.metadata
    )
    return result


@router.post("/chat", response_model=ChatResponse, summary="Send message to JARVIS Autonomous Agent (Legacy / Direct)")
def chat_with_assistant(chat_in: ChatRequest, db: Session = Depends(get_db)):
    """
    Maintains backward compatibility with previous ChatResponse callers while running the Agent Brain.
    """
    if not chat_in.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be blank."
        )

    agent_result = jarvis_agent.process(
        db=db,
        message=chat_in.message.strip(),
        conversation_id=chat_in.conversation_id
    )

    primary_tool = None
    if agent_result.get("actions"):
        primary_tool = agent_result["actions"][0].get("tool_name")

    plan_names = [
        f"Step {s['step_number']}: {s.get('tool_name') or 'Reasoning'}"
        for s in agent_result.get("plan", [])
    ]

    return ChatResponse(
        message=agent_result["response"],
        intent=agent_result["intent"],
        plan=plan_names,
        tool=primary_tool,
        status="completed" if agent_result["agent_state"] != "ERROR" else "failed",
        verified=any(v.get("status") == "VERIFIED" for v in agent_result.get("verification", [])),
        conversation_id=agent_result.get("conversation_id"),
        context_token=chat_in.context_token or "#CTX-78440",
        memory_accessed=agent_result.get("memory_accessed"),
        details={
            "confidence": agent_result["confidence"],
            "execution_time_ms": agent_result["execution_time_ms"],
            "agent_state": agent_result["agent_state"],
            "actions": agent_result.get("actions", []),
            "verification": agent_result.get("verification", [])
        }
    )


@router.get("/tools", response_model=List[Dict[str, Any]], summary="List all safe tools available to the JARVIS Agent")
def list_agent_tools():
    """Returns the catalog of authorized application tools and their input schemas."""
    return agent_tool_registry.list_tools()


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse, summary="Get conversation history")
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """Retrieves full conversation turns and context for a specific session."""
    conv = assistant_service.get_conversation_history(db, conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation #{conversation_id} not found."
        )
    return conv


@router.get("/system-status", response_model=Dict[str, Any], summary="Get agent subsystem status")
def get_system_status():
    """Returns safe diagnostic metrics for operating HUD status strips."""
    tool = SystemInfoTool()
    return tool.execute({})
