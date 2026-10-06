import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from app.ai.intent import IntentDetectionResult
from app.ai.context import AgentContext
from app.ai.tools import agent_tool_registry

logger = logging.getLogger("jarvis.ai.planner")


class PlanStep(BaseModel):
    step_number: int
    tool_name: Optional[str] = None
    parameters: Dict[str, Any] = {}
    risk_level: str = "LOW_RISK"
    status: str = "PENDING"  # PENDING, EXECUTING, COMPLETED, FAILED


class ExecutionPlan(BaseModel):
    goal: str
    intent: str
    steps: List[PlanStep] = []
    needs_confirmation: bool = False
    validation_status: str = "VALID"
    validation_error: Optional[str] = None


class PlanValidator:
    """Validates plans before execution to enforce security and parameter integrity."""

    MAX_STEPS = 5

    def validate(self, plan: ExecutionPlan) -> Tuple[bool, Optional[str]]:
        if len(plan.steps) > self.MAX_STEPS:
            return False, f"Plan exceeds maximum allowed steps limit ({self.MAX_STEPS})."

        for step in plan.steps:
            if step.tool_name:
                if not agent_tool_registry.has_tool(step.tool_name):
                    return False, f"Unauthorized or unknown tool requested: '{step.tool_name}'."

                tool = agent_tool_registry.get_tool(step.tool_name)
                # Verify required parameters
                required_props = tool.input_schema.get("required", [])
                for prop in required_props:
                    if prop not in step.parameters or not step.parameters[prop]:
                        is_dynamic = False
                        if prop == "image_data":
                            earlier_steps = [s for s in plan.steps if s.step_number < step.step_number]
                            if any(s.tool_name in ["local_capture_screen", "capture_screen"] for s in earlier_steps):
                                is_dynamic = True
                        if not is_dynamic:
                            return False, f"Tool '{step.tool_name}' missing required parameter '{prop}'."

        return True, None


class AgentPlanner:
    """
    Structured Agent Planner:
    Decomposes user goals into validated, safe execution steps.
    """

    def __init__(self):
        self.validator = PlanValidator()

    def create_plan(
        self,
        intent_res: IntentDetectionResult,
        context: AgentContext
    ) -> ExecutionPlan:
        intent = intent_res.intent
        entities = intent_res.entities
        goal = intent_res.raw_input
        steps: List[PlanStep] = []

        if intent == "CREATE_TASK":
            title = entities.get("task_title") or goal
            params = {
                "title": title,
                "priority": entities.get("priority", "HIGH"),
                "category": entities.get("category", "General")
            }
            steps.append(PlanStep(
                step_number=1,
                tool_name="task_create",
                parameters=params,
                risk_level="LOW_RISK"
            ))

        elif intent == "LIST_TASKS":
            steps.append(PlanStep(
                step_number=1,
                tool_name="task_list",
                parameters={"limit": 20},
                risk_level="LOW_RISK"
            ))

        elif intent == "UPDATE_TASK":
            task_id = entities.get("task_id")
            if not task_id and context.relevant_tasks:
                task_id = context.relevant_tasks[0].get("id")

            params = {"task_id": task_id}
            if "status" in entities:
                params["status"] = entities["status"]
            if "priority" in entities:
                params["priority"] = entities["priority"]

            steps.append(PlanStep(
                step_number=1,
                tool_name="task_update",
                parameters=params,
                risk_level="LOW_RISK"
            ))

        elif intent == "DELETE_TASK":
            task_id = entities.get("task_id")
            steps.append(PlanStep(
                step_number=1,
                tool_name="task_delete",
                parameters={"task_id": task_id},
                risk_level="MEDIUM_RISK"
            ))

        elif intent == "CREATE_PROJECT":
            name = entities.get("project_name") or "New Project"
            steps.append(PlanStep(
                step_number=1,
                tool_name="project_create",
                parameters={"name": name, "description": goal},
                risk_level="LOW_RISK"
            ))

        elif intent == "PROJECT_ANALYSIS":
            steps.append(PlanStep(
                step_number=1,
                tool_name="project_analyzer",
                parameters={"project_path": goal},
                risk_level="LOW_RISK"
            ))

        elif intent == "PROJECT_QUERY":
            steps.append(PlanStep(
                step_number=1,
                tool_name="project_list",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "MEMORY_QUERY":
            steps.append(PlanStep(
                step_number=1,
                tool_name="memory_search",
                parameters={"query": goal},
                risk_level="LOW_RISK"
            ))

        elif intent == "MEMORY_SAVE":
            content = entities.get("memory_content") or goal
            steps.append(PlanStep(
                step_number=1,
                tool_name="memory_create",
                parameters={"content": content, "importance": 0.90},
                risk_level="LOW_RISK"
            ))

        elif intent == "SYSTEM_STATUS":
            steps.append(PlanStep(
                step_number=1,
                tool_name="system_status",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "OPEN_APPLICATION":
            app_target = entities.get("application") or goal
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_open_application",
                parameters={"application": app_target},
                risk_level="LOW_RISK"
            ))

        elif intent == "OPEN_URL":
            url_target = entities.get("url") or goal
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_open_url",
                parameters={"url": url_target},
                risk_level="LOW_RISK"
            ))

        elif intent == "GET_SYSTEM_INFO":
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_get_system_info",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "GET_CURRENT_TIME":
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_get_current_time",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "LIST_ALLOWED_DIRECTORY":
            dir_target = entities.get("directory") or "Desktop"
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_list_directory",
                parameters={"directory": dir_target},
                risk_level="MEDIUM_RISK"
            ))

        elif intent == "OPEN_FILE":
            file_target = entities.get("file_path") or goal
            steps.append(PlanStep(
                step_number=1,
                tool_name="local_open_file",
                parameters={"file_path": file_target},
                risk_level="MEDIUM_RISK"
            ))

        # Multimodal & Vision Intelligence (Step 9)
        elif intent in ["SCREEN_ANALYSIS", "SCREEN_CONTEXT_REQUEST"]:
            mode = "ui_elements" if intent == "SCREEN_CONTEXT_REQUEST" else "screen_describe"
            has_image = bool(getattr(context, "visual_context", None) and context.visual_context.get("image_data"))
            if has_image:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="vision_analysis",
                    parameters={"image_data": context.visual_context["image_data"], "prompt": goal, "mode": mode},
                    risk_level="LOW_RISK"
                ))
            else:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="local_capture_screen",
                    parameters={},
                    risk_level="LOW_RISK"
                ))
                steps.append(PlanStep(
                    step_number=2,
                    tool_name="vision_analysis",
                    parameters={"prompt": goal, "mode": mode},
                    risk_level="LOW_RISK"
                ))

        elif intent == "OCR_REQUEST":
            has_image = bool(getattr(context, "visual_context", None) and context.visual_context.get("image_data"))
            if has_image:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="vision_ocr",
                    parameters={"image_data": context.visual_context["image_data"]},
                    risk_level="LOW_RISK"
                ))
            else:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="local_capture_screen",
                    parameters={},
                    risk_level="LOW_RISK"
                ))
                steps.append(PlanStep(
                    step_number=2,
                    tool_name="vision_ocr",
                    parameters={},
                    risk_level="LOW_RISK"
                ))

        elif intent in ["VISION_QUERY", "IMAGE_ANALYSIS", "VISUAL_EXPLANATION"]:
            mode = "error_check" if intent == "VISION_QUERY" else "explain"
            has_image = bool(getattr(context, "visual_context", None) and context.visual_context.get("image_data"))
            if has_image:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="vision_analysis",
                    parameters={"image_data": context.visual_context["image_data"], "prompt": goal, "mode": mode},
                    risk_level="LOW_RISK"
                ))
            else:
                steps.append(PlanStep(
                    step_number=1,
                    tool_name="local_capture_screen",
                    parameters={},
                    risk_level="LOW_RISK"
                ))
                steps.append(PlanStep(
                    step_number=2,
                    tool_name="vision_analysis",
                    parameters={"prompt": goal, "mode": mode},
                    risk_level="LOW_RISK"
                ))


        elif intent == "BLOCKED_COMMAND":
            plan = ExecutionPlan(
                goal=goal,
                intent=intent,
                steps=[],
                needs_confirmation=False
            )
            plan.validation_status = "INVALID"
            plan.validation_error = "Arbitrary system commands cannot be executed."
            return plan

        # Build plan
        plan = ExecutionPlan(
            goal=goal,
            intent=intent,
            steps=steps,
            needs_confirmation=any(s.risk_level == "HIGH_RISK" for s in steps)
        )

        # Validate plan
        is_valid, error = self.validator.validate(plan)
        if not is_valid:
            plan.validation_status = "INVALID"
            plan.validation_error = error
            logger.warning(f"Plan validation failed: {error}")
        else:
            plan.validation_status = "VALID"

        return plan


agent_planner = AgentPlanner()
task_planner = agent_planner
