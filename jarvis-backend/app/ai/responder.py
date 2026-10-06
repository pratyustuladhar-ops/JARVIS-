import logging
from typing import Dict, Any, List, Optional
from app.ai.providers import get_ai_provider
from app.ai.planner import ExecutionPlan
from app.ai.executor import ExecutionResult
from app.ai.verifier import VerificationResult
from app.ai.context import AgentContext

logger = logging.getLogger("jarvis.ai.responder")


class ResponseGenerator:
    """
    Response Generation Layer:
    Formulates clear, natural, and concise agent responses incorporating tool outputs and verification.
    """

    def generate(
        self,
        user_message: str,
        intent: str,
        plan: ExecutionPlan,
        execution_results: List[ExecutionResult],
        verification_results: List[VerificationResult],
        context: AgentContext
    ) -> str:
        # Check for plan validation errors
        if plan.validation_status == "INVALID":
            if intent == "BLOCKED_COMMAND":
                return "I can't execute arbitrary system commands. Only pre-approved Windows tools from the allowlist are permitted."
            return f"I understood your request, but could not proceed: {plan.validation_error}"

        # If a tool failed
        for res in execution_results:
            if res.status != "SUCCESS":
                err_str = str(res.error).lower()
                if "allowlist" in err_str or "not in the approved allowlist" in err_str:
                    return "I don't have permission to open that application. Only pre-approved applications (Chrome, Edge, VS Code, Spotify, Notepad, Calculator, Explorer, Terminal) can be launched."
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

        # If verification failed
        for v in verification_results:
            if v.status == "FAILED":
                if v.tool == "local_open_application":
                    return v.detail
                if "text" in v.detail.lower() or "read" in v.detail.lower():
                    return "I couldn't reliably read the text in that image."
                return f"Action executed, but database verification failed: {v.detail}"

        # Direct Multimodal Result Synthesis
        for res in execution_results:
            if res.status == "SUCCESS" and res.tool_name == "vision_analysis" and isinstance(res.output, dict):
                summary = res.output.get("summary")
                if summary:
                    return summary
            if res.status == "SUCCESS" and res.tool_name == "vision_ocr" and isinstance(res.output, dict):
                text = res.output.get("extracted_text", "")
                if text:
                    return f"Here is the text extracted from the visual buffer:\n\n{text}"

        # Use AI provider to generate natural response
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
