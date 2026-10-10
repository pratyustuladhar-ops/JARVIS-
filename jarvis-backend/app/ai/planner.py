import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from app.ai.intent import IntentDetectionResult
from app.ai.context import AgentContext
from app.ai.tools import agent_tool_registry

logger = logging.getLogger("jarvis.ai.planner")


class PlanStep(BaseModel):
    step_number: int = 1
    step_id: int = 1
    tool_name: Optional[str] = None
    tool: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int] = Field(default_factory=list)
    risk_level: str = "LOW_RISK"
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, VERIFIED

    def __init__(self, **data):
        if "step_id" in data and "step_number" not in data:
            data["step_number"] = data["step_id"]
        elif "step_number" in data and "step_id" not in data:
            data["step_id"] = data["step_number"]

        if "tool" in data and "tool_name" not in data:
            data["tool_name"] = data["tool"]
        elif "tool_name" in data and "tool" not in data:
            data["tool"] = data["tool_name"]

        if "arguments" in data and "parameters" not in data:
            data["parameters"] = data["arguments"]
        elif "parameters" in data and "arguments" not in data:
            data["arguments"] = data["parameters"]

        super().__init__(**data)

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name == "step_number" and getattr(self, "step_id", None) != value:
            super().__setattr__("step_id", value)
        elif name == "step_id" and getattr(self, "step_number", None) != value:
            super().__setattr__("step_number", value)
        elif name == "tool_name" and getattr(self, "tool", None) != value:
            super().__setattr__("tool", value)
        elif name == "tool" and getattr(self, "tool_name", None) != value:
            super().__setattr__("tool_name", value)
        elif name == "parameters" and getattr(self, "arguments", None) != value:
            super().__setattr__("arguments", value)
        elif name == "arguments" and getattr(self, "parameters", None) != value:
            super().__setattr__("parameters", value)


class ExecutionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    goal: str
    intent: str
    steps: List[PlanStep] = []
    needs_confirmation: bool = False
    validation_status: str = "VALID"
    validation_error: Optional[str] = None


class PlanValidator:
    """Validates plans before execution to enforce security, dependencies, and parameter integrity."""

    MAX_STEPS = 6
    MAX_PLAN_STEPS = 10

    FORBIDDEN_TOOLS = {
        "powershell", "cmd", "bash", "sh", "python", "shell",
        "terminal_exec", "eval", "exec", "execute_command", "run_script", "run_command"
    }

    def validate(self, plan: ExecutionPlan) -> Tuple[bool, Optional[str]]:
        max_allowed = self.MAX_PLAN_STEPS if plan.intent in ["MULTI_STEP_COMMAND", "BROWSER_SEARCH"] else self.MAX_STEPS
        if len(plan.steps) > max_allowed:
            return False, f"Plan exceeds maximum allowed steps limit ({max_allowed})."

        for step in plan.steps:
            tool_name = step.tool_name or step.tool
            if not tool_name:
                return False, f"Step {step.step_number} has no executable tool assigned."

            norm_tool = tool_name.strip().lower()
            if norm_tool in self.FORBIDDEN_TOOLS or any(fb in norm_tool for fb in ["powershell", "cmd", "bash", "shell"]):
                return False, "Arbitrary system commands cannot be executed."

            if not agent_tool_registry.has_tool(tool_name):
                return False, f"Unauthorized or unknown tool requested: '{tool_name}'."

            tool = agent_tool_registry.get_tool(tool_name)
            params = step.parameters or step.arguments or {}

            # Centralized URL security check
            if "url" in params and params["url"]:
                from app.services.browser.security import URLSecurityValidator, BrowserSecurityError
                try:
                    URLSecurityValidator.validate(params["url"])
                except BrowserSecurityError as bse:
                    return False, f"Navigation blocked: {bse}"

            # Verify required parameters
            required_props = tool.input_schema.get("required", []) if hasattr(tool, "input_schema") else []
            for prop in required_props:
                if prop not in params or params[prop] is None:
                    is_dynamic = False
                    if prop == "image_data":
                        earlier_steps = [s for s in plan.steps if s.step_number < step.step_number]
                        if any((s.tool_name or s.tool) in ["local_capture_screen", "capture_screen"] for s in earlier_steps):
                            is_dynamic = True
                    if not is_dynamic:
                        return False, f"Tool '{tool_name}' missing required parameter '{prop}'."

            # Verify step dependencies
            if step.depends_on:
                for dep in step.depends_on:
                    if dep >= step.step_number or dep < 1:
                        return False, f"Invalid step dependency ({dep}) for step {step.step_number}."

        return True, None


class AgentPlanner:
    """
    Structured Agent Planner:
    Decomposes single-turn and multi-step user goals into validated, safe execution steps.
    """

    def __init__(self):
        self.validator = PlanValidator()

    def _plan_single_step(
        self,
        intent: str,
        entities: Dict[str, Any],
        goal: str,
        step_number: int,
        context: Optional[AgentContext] = None
    ) -> PlanStep:
        """Constructs an individual safe PlanStep based on resolved intent and entities."""
        if intent == "CREATE_TASK":
            title = entities.get("task_title") or goal
            params = {
                "title": title,
                "priority": entities.get("priority", "HIGH"),
                "category": entities.get("category", "General")
            }
            return PlanStep(
                step_number=step_number,
                tool_name="task_create",
                parameters=params,
                risk_level="LOW_RISK"
            )

        elif intent == "LIST_TASKS":
            return PlanStep(
                step_number=step_number,
                tool_name="task_list",
                parameters={"limit": 20},
                risk_level="LOW_RISK"
            )

        elif intent == "UPDATE_TASK":
            task_id = entities.get("task_id")
            if not task_id and context and context.relevant_tasks:
                task_id = context.relevant_tasks[0].get("id")

            params = {"task_id": task_id}
            if "status" in entities:
                params["status"] = entities["status"]
            if "priority" in entities:
                params["priority"] = entities["priority"]

            return PlanStep(
                step_number=step_number,
                tool_name="task_update",
                parameters=params,
                risk_level="LOW_RISK"
            )

        elif intent == "DELETE_TASK":
            task_id = entities.get("task_id")
            return PlanStep(
                step_number=step_number,
                tool_name="task_delete",
                parameters={"task_id": task_id},
                risk_level="MEDIUM_RISK"
            )

        elif intent == "CREATE_PROJECT":
            name = entities.get("project_name") or "New Project"
            return PlanStep(
                step_number=step_number,
                tool_name="project_create",
                parameters={"name": name, "description": goal},
                risk_level="LOW_RISK"
            )

        elif intent == "PROJECT_ANALYSIS":
            return PlanStep(
                step_number=step_number,
                tool_name="project_analyzer",
                parameters={"project_path": goal},
                risk_level="LOW_RISK"
            )

        elif intent == "PROJECT_QUERY":
            return PlanStep(
                step_number=step_number,
                tool_name="project_list",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "MEMORY_QUERY":
            return PlanStep(
                step_number=step_number,
                tool_name="memory_search",
                parameters={"query": goal},
                risk_level="LOW_RISK"
            )

        elif intent == "MEMORY_SAVE":
            content = entities.get("memory_content") or goal
            return PlanStep(
                step_number=step_number,
                tool_name="memory_create",
                parameters={"content": content, "importance": 0.90},
                risk_level="LOW_RISK"
            )

        elif intent == "SYSTEM_STATUS":
            return PlanStep(
                step_number=step_number,
                tool_name="system_status",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "OPEN_APPLICATION":
            app_target = entities.get("application") or goal
            app_low = str(app_target).lower().strip().rstrip(".?!,:;")
            if app_low in ["my browser", "browser", "the browser", "default browser", "web browser"]:
                preferred_browser = "chrome"
                if context and context.relevant_memories:
                    for mem in context.relevant_memories:
                        m_text = str(mem.get("content", "")).lower()
                        if "chrome" in m_text:
                            preferred_browser = "chrome"
                            break
                        elif "edge" in m_text:
                            preferred_browser = "edge"
                            break
                app_target = preferred_browser
            else:
                app_target = app_low

            return PlanStep(
                step_number=step_number,
                tool_name="local_open_application",
                parameters={"application": app_target},
                risk_level="LOW_RISK"
            )

        elif intent == "BROWSER_NAVIGATE":
            url_target = entities.get("url") or goal
            return PlanStep(
                step_number=step_number,
                tool_name="browser_navigate",
                parameters={"url": url_target},
                risk_level="LOW_RISK"
            )

        elif intent == "BROWSER_PAGE_INFO":
            return PlanStep(
                step_number=step_number,
                tool_name="browser_get_page_info",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "BROWSER_CLOSE":
            return PlanStep(
                step_number=step_number,
                tool_name="browser_close",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "OPEN_URL":
            url_target = entities.get("url") or goal
            return PlanStep(
                step_number=step_number,
                tool_name="local_open_url",
                parameters={"url": url_target},
                risk_level="LOW_RISK"
            )

        elif intent == "GET_SYSTEM_INFO":
            return PlanStep(
                step_number=step_number,
                tool_name="local_get_system_info",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "GET_CURRENT_TIME":
            return PlanStep(
                step_number=step_number,
                tool_name="local_get_current_time",
                parameters={},
                risk_level="LOW_RISK"
            )

        elif intent == "LIST_ALLOWED_DIRECTORY":
            dir_target = entities.get("directory") or "Desktop"
            return PlanStep(
                step_number=step_number,
                tool_name="local_list_directory",
                parameters={"directory": dir_target},
                risk_level="MEDIUM_RISK"
            )

        elif intent == "OPEN_FILE":
            file_target = entities.get("file_path") or goal
            return PlanStep(
                step_number=step_number,
                tool_name="local_open_file",
                parameters={"file_path": file_target},
                risk_level="MEDIUM_RISK"
            )

        elif intent == "OPEN_FOLDER":
            folder_target = entities.get("folder_path") or entities.get("directory") or "Desktop"
            return PlanStep(
                step_number=step_number,
                tool_name="local_open_folder",
                parameters={"folder_path": folder_target},
                risk_level="MEDIUM_RISK"
            )

        elif intent == "BLOCKED_COMMAND":
            return PlanStep(
                step_number=step_number,
                tool_name="powershell",
                parameters={"command": goal},
                risk_level="HIGH_RISK"
            )

        # Fallback single step
        return PlanStep(
            step_number=step_number,
            tool_name="system_status" if "status" in goal.lower() else None,
            parameters={},
            risk_level="LOW_RISK"
        )

    def create_plan(
        self,
        intent_res: IntentDetectionResult,
        context: AgentContext
    ) -> ExecutionPlan:
        intent = intent_res.intent
        entities = intent_res.entities
        goal = intent_res.raw_input
        steps: List[PlanStep] = []

        # Multi-Step Command Branch
        if intent == "MULTI_STEP_COMMAND":
            sub_commands = entities.get("sub_commands", [])
            if not sub_commands:
                from app.ai.decomposer import multi_step_decomposer
                sub_commands = multi_step_decomposer.decompose(goal)

            # Enforce MAX_PLAN_STEPS limit
            if len(sub_commands) > self.validator.MAX_PLAN_STEPS:
                plan = ExecutionPlan(
                    goal=goal,
                    intent=intent,
                    steps=[
                        PlanStep(step_number=i + 1, tool_name="task_list")
                        for i in range(len(sub_commands))
                    ]
                )
                plan.validation_status = "INVALID"
                plan.validation_error = f"Plan exceeds maximum allowed steps limit ({self.validator.MAX_PLAN_STEPS})."
                return plan

            from app.ai.intent import intent_detector
            executed_tools = []
            for idx, sub_cmd in enumerate(sub_commands):
                step_num = idx + 1
                dep = [idx] if idx > 0 else []

                sub_res = intent_detector.detect(sub_cmd)
                if sub_res.intent == "BLOCKED_COMMAND":
                    plan = ExecutionPlan(
                        goal=goal,
                        intent=intent,
                        steps=[],
                        validation_status="INVALID",
                        validation_error="Arbitrary system commands cannot be executed."
                    )
                    return plan

                # If preceded by local_open_application in the same multi-step command, use local_open_url
                if sub_res.intent == "OPEN_URL" and "local_open_application" in executed_tools:
                    step = PlanStep(
                        step_number=step_num,
                        tool_name="local_open_url",
                        parameters={"url": sub_res.entities.get("url") or sub_cmd},
                        risk_level="LOW_RISK"
                    )
                else:
                    step = self._plan_single_step(
                        intent=sub_res.intent,
                        entities=sub_res.entities,
                        goal=sub_cmd,
                        step_number=step_num,
                        context=context
                    )
                step.depends_on = dep
                steps.append(step)
                executed_tools.append(step.tool_name or step.tool)

        # Step 9.2: Intelligent Browser Automation Workflows
        elif intent == "BROWSER_SEARCH":
            site = entities.get("site", "youtube").lower()
            query = entities.get("query", goal)
            url = entities.get("url") or ("https://www.google.com" if site == "google" else "https://www.youtube.com")

            if "google" in site or "google" in url:
                search_selector = 'textarea[name="q"], input[name="q"]'
                results_selector = "#search, #rso, div.g"
            else:
                search_selector = 'input[name="search_query"], input#search, [name="search_query"]'
                results_selector = "ytd-video-renderer, ytd-item-section-renderer, #contents"

            steps.append(PlanStep(
                step_number=1,
                tool_name="browser_navigate",
                parameters={"url": url},
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=2,
                tool_name="browser_fill_input",
                parameters={"selector": search_selector, "text": query},
                depends_on=[1],
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=3,
                tool_name="browser_press_key",
                parameters={"key": "Enter"},
                depends_on=[2],
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=4,
                tool_name="browser_wait_for_state",
                parameters={"selector": results_selector, "state": "networkidle"},
                depends_on=[3],
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=5,
                tool_name="browser_get_page_info",
                parameters={},
                depends_on=[4],
                risk_level="LOW_RISK"
            ))

        elif intent == "BROWSER_NAVIGATE":
            url = entities.get("url") or goal
            steps.append(PlanStep(
                step_number=1,
                tool_name="browser_navigate",
                parameters={"url": url},
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=2,
                tool_name="browser_get_page_info",
                parameters={},
                depends_on=[1],
                risk_level="LOW_RISK"
            ))

        elif intent == "BROWSER_PAGE_INFO":
            steps.append(PlanStep(
                step_number=1,
                tool_name="browser_get_page_info",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "BROWSER_CLOSE":
            steps.append(PlanStep(
                step_number=1,
                tool_name="browser_close",
                parameters={},
                risk_level="LOW_RISK"
            ))

        elif intent == "OPEN_URL":
            url = entities.get("url") or goal
            # Standalone Workflow A: Controlled browser navigation and verification
            steps.append(PlanStep(
                step_number=1,
                tool_name="browser_navigate",
                parameters={"url": url},
                risk_level="LOW_RISK"
            ))
            steps.append(PlanStep(
                step_number=2,
                tool_name="browser_get_page_info",
                parameters={},
                depends_on=[1],
                risk_level="LOW_RISK"
            ))

        # Multimodal & Vision Intelligence
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
                    depends_on=[1],
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
                    depends_on=[1],
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
                    depends_on=[1],
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

        else:
            # Single-step dispatch
            step = self._plan_single_step(intent, entities, goal, step_number=1, context=context)
            if step.tool_name or step.parameters:
                steps.append(step)

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
