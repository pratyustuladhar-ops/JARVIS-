import logging
from typing import Dict, Any, List, Optional
from app.ai.providers import get_ai_provider
from app.ai.planner import ExecutionPlan, PlanStep
from app.ai.executor import ExecutionResult
from app.ai.verifier import VerificationResult
from app.ai.context import AgentContext

logger = logging.getLogger("jarvis.ai.responder")


class ResponseGenerator:
    """
    Response Generation Layer:
    Formulates clear, natural, and concise agent responses incorporating tool outputs,
    step dependencies, verification outcomes, and truthful error reporting.
    """

    def _describe_step(
        self,
        step: PlanStep,
        exec_res: Optional[ExecutionResult] = None,
        verif_res: Optional[VerificationResult] = None
    ) -> str:
        tool = step.tool_name or step.tool or ""
        params = step.parameters or step.arguments or {}
        output = exec_res.output if exec_res else {}

        if tool == "local_open_application":
            app = params.get("application", "Application").title()
            if isinstance(output, dict) and output.get("already_running"):
                return f"{app} is already running"
            return f"{app} is open"

        if tool == "local_open_url":
            url = params.get("url", "")
            if "youtube" in url.lower():
                return "YouTube is open"
            if "google" in url.lower():
                return "Google is open"
            if "github" in url.lower():
                return "GitHub is open"
            return f"{url} is open"

        # Step 9.2: Browser Automation Step Descriptions
        if tool == "browser_open":
            return "browser session started"

        if tool == "browser_navigate":
            url = params.get("url", "")
            if "youtube" in url.lower():
                return "navigated to YouTube"
            if "google" in url.lower():
                return "navigated to Google"
            if "github" in url.lower():
                return "navigated to GitHub"
            return f"navigated to {url}"

        if tool == "browser_fill_input":
            txt = params.get("text", "")
            return f"entered query '{txt}'"

        if tool == "browser_press_key":
            return "submitted search"

        if tool == "browser_wait_for_state":
            return "search results loaded"

        if tool == "browser_get_page_info":
            return "verified page state"

        if tool == "browser_close":
            return "closed browser session"

        if tool == "task_create":
            title = params.get("title", "Task")
            return f"Task '{title}' created"

        if tool == "task_list":
            return "Tasks retrieved"

        if tool == "task_update":
            return f"Task #{params.get('task_id', '')} updated"

        if tool == "task_delete":
            return "Task deleted"

        if tool == "project_create":
            name = params.get("name", "Project")
            return f"Project '{name}' created"

        if tool == "project_list":
            return "Projects retrieved"

        if tool == "local_open_folder":
            folder = params.get("folder_path", "Folder").title()
            return f"{folder} is open"

        if tool == "local_open_file":
            f_name = params.get("file_path", "File")
            return f"'{f_name}' is open"

        if tool == "system_status":
            return "system diagnostics verified"

        if tool == "local_get_current_time":
            return "current time retrieved"

        if tool == "local_get_system_info":
            return "system specifications retrieved"

        return f"{tool} completed"

    def generate(
        self,
        user_message: str,
        intent: str,
        plan: ExecutionPlan,
        execution_results: List[ExecutionResult],
        verification_results: List[VerificationResult],
        context: AgentContext
    ) -> str:
        # 1. Check for plan validation errors
        if plan.validation_status == "INVALID":
            if intent == "BLOCKED_COMMAND" or any(w in user_message.lower() for w in ["powershell", "cmd", "bash", "shell"]):
                return "I can't execute arbitrary system commands. Only pre-approved Windows tools from the allowlist are permitted."
            if "Navigation blocked" in str(plan.validation_error) or "blocked" in str(plan.validation_error).lower():
                return "Navigation blocked: The requested destination is not permitted by JARVIS security policies (private, internal, or unsupported URL)."
            return f"I understood your request, but could not proceed: {plan.validation_error}"

        # 2. Specialized Single-Turn Browser Information Query
        if intent == "BROWSER_PAGE_INFO":
            for res in execution_results:
                if res.status == "SUCCESS" and res.tool_name == "browser_get_page_info" and isinstance(res.output, dict):
                    title = res.output.get("title")
                    if title:
                        return f'The title of the active webpage is: "{title}".'
            for res in execution_results:
                if res.status != "SUCCESS":
                    return f"Failed retrieving page information: {res.error}"
            return "No active webpage title could be retrieved."

        if intent == "BROWSER_CLOSE":
            return "Done. The controlled browser session has been closed cleanly."

        # 3. Multi-Step Execution Responses
        if len(plan.steps) > 1 or intent in ["MULTI_STEP_COMMAND", "BROWSER_SEARCH", "BROWSER_NAVIGATE", "OPEN_URL"]:
            # Check for failure in any step
            failed_idx = None
            for idx, res in enumerate(execution_results):
                if res.status != "SUCCESS":
                    failed_idx = idx
                    break

            if failed_idx is None:
                for idx, v in enumerate(verification_results):
                    if v.status != "VERIFIED":
                        failed_idx = idx
                        break

            if failed_idx is None:
                for idx, step in enumerate(plan.steps):
                    if step.status != "VERIFIED":
                        failed_idx = idx
                        break

            if failed_idx is not None:
                # Step 1 failed
                if failed_idx == 0:
                    step1 = plan.steps[0]
                    target = step1.parameters.get("application") or step1.parameters.get("title") or step1.parameters.get("url") or "the first action"
                    target_str = str(target).title() if isinstance(target, str) else "the action"
                    if step1.tool_name == "local_open_application":
                        return f"I couldn't open {target_str}, so I didn't continue with the next step."
                    if step1.tool_name == "browser_navigate":
                        return "I couldn't navigate to the requested webpage, so I didn't continue with the next step."
                    return f"I couldn't complete {target_str}, so I didn't continue with the next step."
                else:
                    # Step K failed after Step 1 succeeded
                    step1_desc = self._describe_step(
                        plan.steps[0],
                        execution_results[0] if execution_results else None,
                        verification_results[0] if verification_results else None
                    )
                    failed_step = plan.steps[failed_idx]
                    failed_target = (
                        failed_step.parameters.get("url") or
                        failed_step.parameters.get("application") or
                        failed_step.parameters.get("title") or
                        failed_step.tool_name or
                        "subsequent"
                    )
                    if "youtube" in str(failed_target).lower():
                        failed_target_str = "YouTube"
                    elif "chrome" in str(failed_target).lower():
                        failed_target_str = "Chrome"
                    elif "spotify" in str(failed_target).lower():
                        failed_target_str = "Spotify"
                    else:
                        failed_target_str = str(failed_target).title()
                    return f"{step1_desc}, but I couldn't complete the {failed_target_str} step."

            # Dedicated Clean Formulations for Verified Browser Workflows
            if intent == "BROWSER_SEARCH":
                query = ""
                for s in plan.steps:
                    if s.tool_name == "browser_fill_input":
                        query = s.parameters.get("text", "")
                site_name = "YouTube" if "youtube" in user_message.lower() else ("Google" if "google" in user_message.lower() else "the website")
                return f"Done. Navigated to {site_name}, searched for '{query}', and verified that search results appeared."

            if intent in ["BROWSER_NAVIGATE", "OPEN_URL"] and any(s.tool_name == "browser_navigate" for s in plan.steps):
                site_name = "YouTube" if "youtube" in user_message.lower() else ("Google" if "google" in user_message.lower() else "the website")
                return f"Done. Navigated to {site_name} and verified the page state."

            # All steps succeeded and verified!
            step_descs = []
            for i, step in enumerate(plan.steps):
                exec_r = execution_results[i] if i < len(execution_results) else None
                verif_r = verification_results[i] if i < len(verification_results) else None
                step_descs.append(self._describe_step(step, exec_r, verif_r))

            if len(step_descs) == 2:
                return f"Done. {step_descs[0]} and {step_descs[1]}."
            elif len(step_descs) == 3:
                return f"Done. {step_descs[0]}, {step_descs[1]}, and {step_descs[2]}."
            elif len(step_descs) > 3:
                return "Done. " + ", ".join(step_descs[:-1]) + f", and {step_descs[-1]}."
            elif step_descs:
                return f"Done. {step_descs[0]}."

        # 4. Single-step error handling
        for res in execution_results:
            if res.status != "SUCCESS":
                err_str = str(res.error).lower()
                if "allowlist" in err_str or "not in the approved allowlist" in err_str:
                    return "I don't have permission to open that application. Only pre-approved applications (Chrome, Edge, VS Code, Spotify, Notepad, Calculator, Explorer, Terminal) can be launched."
                if res.tool_name and res.tool_name.startswith("browser_"):
                    if "navigation blocked" in err_str or "blocked" in err_str or "unsupported url scheme" in err_str:
                        return "Navigation blocked: The requested destination is not permitted by JARVIS security policies (private, internal, or unsupported URL)."
                    if "unavailable" in err_str or "could not initialize browser" in err_str:
                        return "Browser automation is unavailable: No compatible browser (Microsoft Edge or Google Chrome) could be launched."
                    if "element matching" in err_str or ("not found" in err_str and "element" in err_str):
                        return "I could not locate the requested element on the webpage."
                    if "ambiguous" in err_str or "multiple matching elements" in err_str:
                        return "Multiple matching elements were found. I couldn't safely determine which one to interact with."
                    if "timed out" in err_str or "timeout" in err_str:
                        return "Browser operation timed out."
                    return f"Browser operation failed: {res.error}"
                if "traversal" in err_str or "outside approved" in err_str:
                    return "Access denied. Path traversal and access outside approved user directories (Desktop, Documents, Downloads) is strictly prohibited."
                if "not installed" in err_str or "could not be safely resolved" in err_str or "application_not_found" in err_str or "not found on this system" in err_str:
                    return str(res.error)
                if "ocr" in err_str or "unreadable" in err_str:
                    return "I couldn't reliably read the text in that image."
                if "vision" in err_str or "capture" in err_str:
                    return "I couldn't complete that visual action."
                if res.tool_name == "local_open_application":
                    return str(res.error)
                return f"I encountered an error executing this request: {res.error}"

        # 4. Single-step verification error handling
        for v in verification_results:
            if v.status == "FAILED":
                if v.tool == "local_open_application":
                    return v.detail
                if "text" in v.detail.lower() or "read" in v.detail.lower():
                    return "I couldn't reliably read the text in that image."
                return f"Action executed, but database verification failed: {v.detail}"

        # 5. Direct Multimodal Result Synthesis
        for res in execution_results:
            if res.status == "SUCCESS" and res.tool_name == "vision_analysis" and isinstance(res.output, dict):
                summary = res.output.get("summary")
                if summary:
                    return summary
            if res.status == "SUCCESS" and res.tool_name == "vision_ocr" and isinstance(res.output, dict):
                text = res.output.get("extracted_text", "")
                if text:
                    return f"Here is the text extracted from the visual buffer:\n\n{text}"

        # 6. Provider response synthesis
        provider = get_ai_provider()
        context_payload = {
            "intent": intent,
            "tool_results": [r.to_dict() for r in execution_results],
            "verifications": [v.to_dict() for v in verification_results],
            "relevant_memories": context.relevant_memories,
            "relevant_tasks": context.relevant_tasks,
            "relevant_projects": context.relevant_projects
        }

        response_text = provider.generate_response(user_message, context_payload)
        return response_text


response_generator = ResponseGenerator()
