from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.chat import Conversation, Message
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent_service import agent_service


class AssistantService:
    def chat(self, db: Session, chat_in: ChatRequest) -> ChatResponse:
        # Fetch or create conversation
        conv = None
        if chat_in.conversation_id:
            conv = db.query(Conversation).filter(Conversation.id == chat_in.conversation_id).first()

        if not conv:
            conv = Conversation(
                title=chat_in.message[:40],
                context_token=chat_in.context_token or "#CTX-78440"
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

        # Save user message
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=chat_in.message
        )
        db.add(user_msg)
        db.commit()

        # Run through agent pipeline
        response = agent_service.process_message(
            user_message=chat_in.message,
            db=db,
            conversation_id=conv.id,
            context_token=conv.context_token
        )

        # Save assistant message
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=response.message,
            intent=response.intent
        )
        db.add(assistant_msg)
        db.commit()

        return response

    def get_conversation_history(self, db: Session, conversation_id: int) -> Optional[Conversation]:
        return db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def get_recent_conversations(self, db: Session, limit: int = 10) -> List[Conversation]:
        return db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(limit).all()


assistant_service = AssistantService()
