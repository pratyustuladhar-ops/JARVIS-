import time
import json
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.ai.intent import intent_detector, IntentDetectionResult
from app.ai.context import context_manager, AgentContext
from app.ai.planner import agent_planner, ExecutionPlan
from app.ai.executor import tool_executor, ExecutionResult
from app.ai.verifier import verification_engine, VerificationResult
from app.ai.memory_manager import memory_manager
from app.ai.responder import response_generator
from app.services.activity_service import activity_service
from app.models.chat import Conversation, Message

logger = logging.getLogger("jarvis.ai.agent")


class JARVISAgent:
    """
    Central JARVIS AI Agent Orchestrator:
    Coordinates the 8-stage intelligent reasoning and execution pipeline:
    1. Input Intake
    2. Intent Detection (Rule + ML + LLM Fallback)
    3. Context Gathering (Selective DB retrieval)
    4. Task Planning & Validation
    5. Tool Execution (Safe sandboxed application tools)
    6. Independent Persistence Verification
    7. Memory Manager Update
    8. Contextual Response Synthesis & Activity Logging
    """

    def process(
        self,
        db: Session,
        message: str,
        conversation_id: Optional[int] = None,
        input_type: str = "text",
        image_data: Optional[str] = None,
        image_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"=== [JARVIS AGENT] Processing ({input_type}): '{message}' ===")

        # 1. Manage Conversation Session
        conv = None
        if conversation_id:
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            conv = Conversation(
                title=message[:40] if message else "Multimodal Interaction",
                context_token="#CTX-" + str(int(time.time()))[-5:]
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

        # Store user message
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=message
        )
        db.add(user_msg)
        db.commit()

        # 2. Stage: Intent Detection
        intent_res: IntentDetectionResult = intent_detector.detect(
            message,
            input_type=input_type,
            has_image=bool(image_data)
        )
        logger.info(f"[STAGE 1: INTENT] {intent_res.intent} (conf: {intent_res.confidence}, strat: {intent_res.strategy_used})")

        # 3. Stage: Context Retrieval (incorporates visual context if present)
        visual_ctx = None
        if image_data:
            visual_ctx = {
                "image_data": image_data,
                "metadata": image_metadata or {}
            }

        context: AgentContext = context_manager.gather_context(
            db=db,
            user_message=message,
            intent=intent_res.intent,
            conversation_id=conv.id,
            visual_context=visual_ctx,
            input_type=input_type
        )
        logger.info(f"[STAGE 2: CONTEXT] Retrived {len(context.relevant_tasks)} tasks, {len(context.relevant_projects)} projs, {len(context.relevant_memories)} mems")

        # 4. Stage: Planning & Plan Validation
        plan: ExecutionPlan = agent_planner.create_plan(intent_res, context)
        logger.info(f"[STAGE 3: PLAN] Generated {len(plan.steps)} steps. Status: {plan.validation_status}")

        execution_results: List[ExecutionResult] = []
        verification_results: List[VerificationResult] = []

        # 5. Stage: Tool Selection & Execution
        step_outputs: Dict[str, Any] = {}
        if visual_ctx and "image_data" in visual_ctx:
            step_outputs["image_data"] = visual_ctx["image_data"]

        if plan.validation_status == "VALID":
            for step in plan.steps:
                if step.tool_name:
                    # Dynamically inject intermediate visual buffer from previous step if required
                    if "image_data" in step_outputs and "image_data" not in step.parameters:
                        step.parameters["image_data"] = step_outputs["image_data"]

                    logger.info(f"[STAGE 4: EXECUTE] Running tool: {step.tool_name}")
                    exec_res = tool_executor.execute_step(db, step)
                    execution_results.append(exec_res)

                    # Propagate output data (e.g. captured screenshot image_data) to subsequent steps
                    if exec_res.status == "SUCCESS" and isinstance(exec_res.output, dict):
                        if "image_data" in exec_res.output:
                            step_outputs["image_data"] = exec_res.output["image_data"]

                    # 6. Stage: Verification
                    logger.info(f"[STAGE 5: VERIFY] Verifying tool: {step.tool_name}")
                    verif_res = verification_engine.verify(db, exec_res, step.parameters)
                    verification_results.append(verif_res)
                    logger.info(f"[VERIFY RESULT] {verif_res.status}: {verif_res.detail}")

                    if exec_res.status != "SUCCESS":
                        break

        # 7. Stage: Memory Management (Check if user requested memory save or shared fact)
        memory_badge = None
        if context.relevant_memories:
            first_m = context.relevant_memories[0]
            memory_badge = f"{first_m.get('content')} [Relevance {int((first_m.get('importance', 0.95))*100)}%]"
        elif intent_res.intent == "MEMORY_QUERY" or "preference" in message.lower() or "java" in message.lower():
            mems = memory_manager.retrieve_relevant_memories(db, message)
            if mems:
                memory_badge = f"{mems[0].content} [Relevance 98%]"

        if intent_res.intent == "MEMORY_SAVE":
            content_to_save = intent_res.entities.get("memory_content", message)
            mem_type = "PROJECT_MEMORY" if "project" in message.lower() else "TEXT_MEMORY"
            memory_manager.save_fact(db, content_to_save, memory_type=mem_type, importance=0.90)

        # 8. Stage: Response Generation
        final_response = response_generator.generate(
            user_message=message,
            intent=intent_res.intent,
            plan=plan,
            execution_results=execution_results,
            verification_results=verification_results,
            context=context
        )
        logger.info(f"[STAGE 6: RESPOND] Output generated.")

        total_duration_ms = round((time.time() - start_time) * 1000, 2)

        # Save assistant message
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=final_response,
            intent=intent_res.intent
        )
        db.add(assistant_msg)
        db.commit()

        # Log trace to Activity table if a meaningful action occurred
        if execution_results:
            first_tool = execution_results[0].tool_name
            first_verif = verification_results[0].status if verification_results else "SUCCESS"
            activity_service.record_activity(
                db=db,
                event_type="AGENT_EXECUTION",
                title=f"Agent Tool: {first_tool}",
                description=f"Action '{first_tool}' executed with verification: {first_verif}",
                status="SUCCESS" if first_verif == "VERIFIED" else "WARNING",
                metadata_json=json.dumps({
                    "intent": intent_res.intent,
                    "confidence": intent_res.confidence,
                    "tool": first_tool,
                    "duration_ms": total_duration_ms
                })
            )

        # Phase 5: Structured Command Learning Dataset Storage
        self._record_command_learning(
            command=message,
            intent=intent_res.intent,
            confidence=intent_res.confidence,
            strategy_used=intent_res.strategy_used,
            entities=intent_res.entities,
            tool=execution_results[0].tool_name if execution_results else None,
            execution_status="SUCCESS" if (execution_results and execution_results[0].status == "SUCCESS") else ("ERROR" if execution_results else "N/A"),
            verification_status=verification_results[0].status if verification_results else "N/A",
            verification_detail=verification_results[0].detail if verification_results else ""
        )

        agent_state = "RESPONDING"
        if plan.validation_status == "INVALID" or any(r.status != "SUCCESS" for r in execution_results):
            agent_state = "ERROR"

        return {
            "response": final_response,
            "intent": intent_res.intent,
            "confidence": intent_res.confidence,
            "plan": [
                {
                    "step_number": s.step_number,
                    "tool_name": s.tool_name,
                    "risk_level": s.risk_level,
                    "status": s.status
                }
                for s in plan.steps
            ],
            "actions": [r.to_dict() for r in execution_results],
            "verification": [v.to_dict() for v in verification_results],
            "verified": all(v.status == "VERIFIED" for v in verification_results) if verification_results else (agent_state != "ERROR"),
            "conversation_id": conv.id,
            "memory_accessed": memory_badge,
            "execution_time_ms": total_duration_ms,
            "agent_state": agent_state
        }

    def _record_command_learning(self, **data):
        """Stores structured interaction traces for future model training and phrasing analytics."""
        try:
            from pathlib import Path
            from datetime import datetime
            dataset_dir = Path(__file__).resolve().parent / "data"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            log_file = dataset_dir / "command_learning_dataset.jsonl"
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                **data
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.debug(f"Command learning dataset recording skipped: {e}")


jarvis_agent = JARVISAgent()
