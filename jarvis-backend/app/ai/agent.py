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
    Coordinates the 8-stage intelligent reasoning and multi-step execution pipeline:
    1. Input Intake
    2. Intent Detection (Rule + Multi-Step Decomposer + ML + LLM Fallback)
    3. Context Gathering (Selective DB retrieval)
    4. Task Planning & Validation (Structured Dependency Plans)
    5. Sequential Tool Execution (Safe sandboxed application tools)
    6. Independent Step & Persistence Verification
    7. Memory Manager Update
    8. Contextual Response Synthesis & Granular Activity Logging
    """

    @staticmethod
    def _safe_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
        """Scrubs passwords, auth tokens, secrets, and private credentials from logged metadata."""
        safe = {}
        forbidden = {"token", "auth", "password", "secret", "key", "credential"}
        for k, v in meta.items():
            if any(f in k.lower() for f in forbidden):
                continue
            if isinstance(v, dict):
                safe[k] = JARVISAgent._safe_metadata(v)
            else:
                safe[k] = v
        return safe

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
        logger.info(f"[STAGE 2: CONTEXT] Retrieved {len(context.relevant_tasks)} tasks, {len(context.relevant_projects)} projs, {len(context.relevant_memories)} mems")

        # 4. Stage: Planning & Plan Validation
        plan: ExecutionPlan = agent_planner.create_plan(intent_res, context)
        logger.info(f"[STAGE 3: PLAN] Generated plan {plan.plan_id} with {len(plan.steps)} steps. Status: {plan.validation_status}")

        # Activity Log: PLAN_CREATED
        if plan.steps:
            activity_service.record_activity(
                db=db,
                event_type="PLAN_CREATED",
                title=f"Plan Created: {plan.plan_id}",
                description=f"Generated execution plan with {len(plan.steps)} steps (intent: {plan.intent}).",
                status="INFO" if plan.validation_status == "VALID" else "WARNING",
                metadata_json=json.dumps(self._safe_metadata({
                    "plan_id": plan.plan_id,
                    "intent": plan.intent,
                    "steps_count": len(plan.steps),
                    "validation_status": plan.validation_status
                }))
            )

        execution_results: List[ExecutionResult] = []
        verification_results: List[VerificationResult] = []
        failed_step_number: Optional[int] = None

        # 5. Stage: Sequential Tool Execution with Step Verification
        step_outputs: Dict[str, Any] = {}
        if visual_ctx and "image_data" in visual_ctx:
            step_outputs["image_data"] = visual_ctx["image_data"]

        if plan.validation_status == "VALID":
            step_map = {s.step_number: s for s in plan.steps}

            for step in plan.steps:
                tool_name = step.tool_name or step.tool
                if not tool_name:
                    continue

                # Check step dependencies
                unmet_dep = False
                for dep_id in step.depends_on:
                    dep_step = step_map.get(dep_id)
                    if not dep_step or dep_step.status != "VERIFIED":
                        unmet_dep = True
                        break

                if unmet_dep:
                    logger.warning(f"[EXECUTE] Step {step.step_number} SKIPPED due to unmet dependency {step.depends_on}")
                    step.status = "SKIPPED"
                    failed_step_number = failed_step_number or step.step_number
                    # Mark any subsequent steps as SKIPPED
                    for rem in plan.steps:
                        if rem.step_number > step.step_number:
                            rem.status = "SKIPPED"
                    break

                # Mark step RUNNING & Log Activity
                step.status = "RUNNING"
                activity_service.record_activity(
                    db=db,
                    event_type="STEP_STARTED",
                    title=f"Step {step.step_number} Started: {tool_name}",
                    description=f"Executing step {step.step_number} ({tool_name}) for plan {plan.plan_id}.",
                    status="INFO",
                    metadata_json=json.dumps(self._safe_metadata({
                        "plan_id": plan.plan_id,
                        "step_id": step.step_number,
                        "tool": tool_name
                    }))
                )

                # Inject dynamic inputs if available
                if "image_data" in step_outputs and "image_data" not in step.parameters:
                    step.parameters["image_data"] = step_outputs["image_data"]

                # Execute step
                logger.info(f"[STAGE 4: EXECUTE] Running step {step.step_number}: {tool_name}")
                exec_res = tool_executor.execute_step(db, step)
                execution_results.append(exec_res)

                if exec_res.status != "SUCCESS":
                    step.status = "FAILED"
                    failed_step_number = step.step_number
                    logger.error(f"[EXECUTE FAILED] Step {step.step_number} failed: {exec_res.error}")
                    activity_service.record_activity(
                        db=db,
                        event_type="STEP_FAILED",
                        title=f"Step {step.step_number} Failed: {tool_name}",
                        description=f"Tool execution failed: {exec_res.error}",
                        status="ERROR",
                        metadata_json=json.dumps(self._safe_metadata({
                            "plan_id": plan.plan_id,
                            "step_id": step.step_number,
                            "tool": tool_name,
                            "error": str(exec_res.error)
                        }))
                    )
                    # Mark subsequent steps SKIPPED
                    for rem in plan.steps:
                        if rem.step_number > step.step_number:
                            rem.status = "SKIPPED"
                    break

                activity_service.record_activity(
                    db=db,
                    event_type="STEP_COMPLETED",
                    title=f"Step {step.step_number} Completed: {tool_name}",
                    description=f"Tool completed execution in {exec_res.duration_ms}ms.",
                    status="INFO",
                    metadata_json=json.dumps(self._safe_metadata({
                        "plan_id": plan.plan_id,
                        "step_id": step.step_number,
                        "tool": tool_name,
                        "duration_ms": exec_res.duration_ms
                    }))
                )

                # Propagate outputs if present
                if isinstance(exec_res.output, dict) and "image_data" in exec_res.output:
                    step_outputs["image_data"] = exec_res.output["image_data"]

                # 6. Stage: Step Verification
                logger.info(f"[STAGE 5: VERIFY] Verifying step {step.step_number}: {tool_name}")
                verif_res = verification_engine.verify(db, exec_res, step.parameters)
                verification_results.append(verif_res)
                logger.info(f"[VERIFY RESULT] Step {step.step_number} status: {verif_res.status} ({verif_res.detail})")

                if verif_res.status != "VERIFIED":
                    step.status = "FAILED"
                    failed_step_number = step.step_number
                    activity_service.record_activity(
                        db=db,
                        event_type="STEP_FAILED",
                        title=f"Step {step.step_number} Verification Failed: {tool_name}",
                        description=f"Verification failed: {verif_res.detail}",
                        status="ERROR",
                        metadata_json=json.dumps(self._safe_metadata({
                            "plan_id": plan.plan_id,
                            "step_id": step.step_number,
                            "tool": tool_name,
                            "detail": verif_res.detail
                        }))
                    )
                    # Mark subsequent steps SKIPPED
                    for rem in plan.steps:
                        if rem.step_number > step.step_number:
                            rem.status = "SKIPPED"
                    break

                step.status = "VERIFIED"
                activity_service.record_activity(
                    db=db,
                    event_type="STEP_VERIFIED",
                    title=f"Step {step.step_number} Verified: {tool_name}",
                    description=f"Execution verified: {verif_res.detail}",
                    status="SUCCESS",
                    metadata_json=json.dumps(self._safe_metadata({
                        "plan_id": plan.plan_id,
                        "step_id": step.step_number,
                        "tool": tool_name,
                        "detail": verif_res.detail
                    }))
                )

            # Record Overall Plan Completion / Failure Activity
            if plan.steps:
                if failed_step_number is None and all(s.status == "VERIFIED" for s in plan.steps if (s.tool_name or s.tool)):
                    activity_service.record_activity(
                        db=db,
                        event_type="PLAN_COMPLETED",
                        title=f"Plan Completed: {plan.plan_id}",
                        description=f"All {len(plan.steps)} steps executed and verified successfully.",
                        status="SUCCESS",
                        metadata_json=json.dumps(self._safe_metadata({
                            "plan_id": plan.plan_id,
                            "total_steps": len(plan.steps)
                        }))
                    )
                else:
                    activity_service.record_activity(
                        db=db,
                        event_type="PLAN_FAILED",
                        title=f"Plan Failed: {plan.plan_id}",
                        description=f"Execution halted at step {failed_step_number or 'validation'}.",
                        status="ERROR",
                        metadata_json=json.dumps(self._safe_metadata({
                            "plan_id": plan.plan_id,
                            "failed_step": failed_step_number
                        }))
                    )

        # 7. Stage: Memory Management
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

        # Log trace to Activity table if single action occurred
        if execution_results and len(plan.steps) <= 1:
            first_tool = execution_results[0].tool_name
            first_verif = verification_results[0].status if verification_results else "SUCCESS"
            activity_service.record_activity(
                db=db,
                event_type="AGENT_EXECUTION",
                title=f"Agent Tool: {first_tool}",
                description=f"Action '{first_tool}' executed with verification: {first_verif}",
                status="SUCCESS" if first_verif == "VERIFIED" else "WARNING",
                metadata_json=json.dumps(self._safe_metadata({
                    "intent": intent_res.intent,
                    "confidence": intent_res.confidence,
                    "tool": first_tool,
                    "duration_ms": total_duration_ms
                }))
            )

        # Command Learning Dataset Storage
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

        completed_steps_count = sum(1 for s in plan.steps if s.status == "VERIFIED")
        total_steps_count = len(plan.steps)
        is_success = (
            plan.validation_status == "VALID" and
            (failed_step_number is None) and
            all(s.status == "VERIFIED" for s in plan.steps if (s.tool_name or s.tool)) and
            (not any(r.status != "SUCCESS" for r in execution_results))
        ) if plan.steps else (plan.validation_status == "VALID")

        agent_state = "RESPONDING" if is_success else "ERROR"

        return {
            "response": final_response,
            "intent": intent_res.intent,
            "confidence": intent_res.confidence,
            "plan": [
                {
                    "step_number": s.step_number,
                    "step_id": s.step_number,
                    "tool_name": s.tool_name or s.tool,
                    "tool": s.tool_name or s.tool,
                    "risk_level": s.risk_level,
                    "status": s.status,
                    "depends_on": s.depends_on
                }
                for s in plan.steps
            ],
            "actions": [r.to_dict() for r in execution_results],
            "verification": [v.to_dict() for v in verification_results],
            "verified": is_success,
            "conversation_id": conv.id,
            "memory_accessed": memory_badge,
            "execution_time_ms": total_duration_ms,
            "agent_state": agent_state,
            # Step 9.1 Structured Execution Information
            "plan_id": plan.plan_id,
            "success": is_success,
            "completed_steps": completed_steps_count,
            "total_steps": total_steps_count,
            "failed_step": failed_step_number,
            "steps": [
                {
                    "step_id": s.step_number,
                    "tool": s.tool_name or s.tool,
                    "status": s.status,
                    "depends_on": s.depends_on,
                    "result": execution_results[s.step_number - 1].to_dict() if len(execution_results) >= s.step_number else None
                }
                for s in plan.steps
            ]
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
