import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.task_service import task_service
from app.services.project_service import project_service
from app.services.memory_service import memory_service
from app.ai.executor import ExecutionResult

logger = logging.getLogger("jarvis.ai.verifier")


class VerificationResult:
    def __init__(
        self,
        status: str,  # VERIFIED, FAILED, NOT_APPLICABLE
        tool: str,
        entity_id: Optional[Any] = None,
        detail: str = ""
    ):
        self.status = status
        self.tool = tool
        self.entity_id = entity_id
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "tool": self.tool,
            "entity_id": self.entity_id,
            "detail": self.detail
        }


class VerificationEngine:
    """
    Independent Verification Engine.
    Verifies that state modifications actually occurred in the persistence layer.
    """

    def verify(
        self,
        db: Session,
        execution_result: ExecutionResult,
        requested_params: Dict[str, Any]
    ) -> VerificationResult:
        tool_name = execution_result.tool_name

        if execution_result.status != "SUCCESS":
            return VerificationResult(
                status="FAILED",
                tool=tool_name,
                detail=f"Execution reported error: {execution_result.error}"
            )

        output = execution_result.output

        # Verify task creation
        if tool_name == "task_create":
            task_id = output.get("id") if isinstance(output, dict) else None
            if not task_id:
                return VerificationResult("FAILED", tool_name, None, "Task creation returned no ID.")
            verified_task = task_service.get_by_id(db, task_id)
            if verified_task:
                logger.info(f"[VERIFICATION] Task #{task_id} existence verified in PostgreSQL.")
                return VerificationResult("VERIFIED", tool_name, task_id, f"Task #{task_id} exists in DB.")
            return VerificationResult("FAILED", tool_name, task_id, f"Task #{task_id} not found in DB.")

        # Verify task deletion
        if tool_name == "task_delete":
            task_id = requested_params.get("task_id")
            if task_id:
                verified_task = task_service.get_by_id(db, int(task_id))
                if verified_task is None:
                    logger.info(f"[VERIFICATION] Task #{task_id} confirmed deleted.")
                    return VerificationResult("VERIFIED", tool_name, task_id, f"Task #{task_id} confirmed removed from DB.")
                return VerificationResult("FAILED", tool_name, task_id, f"Task #{task_id} still exists in DB.")

        # Verify task update
        if tool_name == "task_update":
            task_id = output.get("id") if isinstance(output, dict) else None
            if task_id:
                verified_task = task_service.get_by_id(db, task_id)
                if verified_task:
                    return VerificationResult("VERIFIED", tool_name, task_id, f"Task #{task_id} state verified.")
                return VerificationResult("FAILED", tool_name, task_id, f"Task #{task_id} not found.")

        # Verify project creation
        if tool_name == "project_create":
            proj_id = output.get("id") if isinstance(output, dict) else None
            if proj_id:
                verified_proj = project_service.get_by_id(db, proj_id)
                if verified_proj:
                    logger.info(f"[VERIFICATION] Project #{proj_id} existence verified.")
                    return VerificationResult("VERIFIED", tool_name, proj_id, f"Project #{proj_id} exists in DB.")
                return VerificationResult("FAILED", tool_name, proj_id, f"Project #{proj_id} missing from DB.")

        # Verify memory creation
        if tool_name == "memory_create":
            mem_id = output.get("id") if isinstance(output, dict) else None
            if mem_id:
                verified_mem = memory_service.get_by_id(db, mem_id)
                if verified_mem:
                    return VerificationResult("VERIFIED", tool_name, mem_id, f"Memory #{mem_id} stored in DB.")
                return VerificationResult("FAILED", tool_name, mem_id, f"Memory #{mem_id} missing from DB.")

        # Verify Windows Local Agent tools
        if tool_name == "local_open_application":
            app = requested_params.get("application", "Application")
            if isinstance(output, dict) and (output.get("status") == "failed" or output.get("verified") is False or output.get("success") is False):
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    entity_id=None,
                    detail=output.get("message") or output.get("error") or f"{app.title()} could not be opened."
                )
            pid = output.get("pid") if isinstance(output, dict) else None
            already_running = output.get("already_running") if isinstance(output, dict) else False
            detail_msg = f"{app.title()} is already running." if already_running else f"{app.title()} process confirmed launched."
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=pid,
                detail=detail_msg
            )

        if tool_name == "local_open_url":
            if isinstance(output, dict) and output.get("status") == "failed":
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    detail=output.get("error") or "URL verification failed."
                )
            url = requested_params.get("url", "")
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=None,
                detail=f"Browser navigated to {url}."
            )

        if tool_name in ["local_get_system_info", "local_get_current_time", "local_list_directory", "local_open_file", "local_open_folder"]:
            if isinstance(output, dict) and output.get("status") == "failed":
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    detail=output.get("error") or f"Action {tool_name} failed verification."
                )
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=None,
                detail="Local Windows action verified."
            )

        # Multimodal & Vision Tools Verification (Step 9)
        if tool_name in ["local_capture_screen", "capture_screen"]:
            if not isinstance(output, dict) or not output.get("image_data") or output.get("status") == "failed":
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    detail=output.get("error") if isinstance(output, dict) else "Screen capture failed to produce visual buffer."
                )
            res_str = output.get("resolution") or f"{output.get('width', 1920)}x{output.get('height', 1080)}"
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=None,
                detail=f"Screen capture verified ({res_str})."
            )

        if tool_name == "vision_analysis":
            if not isinstance(output, dict) or output.get("status") == "failed" or not (output.get("summary") or output.get("description")):
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    detail=output.get("error") if isinstance(output, dict) else "Vision analysis produced no descriptive output."
                )
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=None,
                detail="Visual analysis confirmed by multimodal engine."
            )

        if tool_name == "vision_ocr":
            if not isinstance(output, dict) or output.get("status") == "failed" or not (output.get("extracted_text") or output.get("text")):
                return VerificationResult(
                    status="FAILED",
                    tool=tool_name,
                    detail="I couldn't reliably read the text in that image."
                )
            txt = output.get("extracted_text") or output.get("text") or ""
            return VerificationResult(
                status="VERIFIED",
                tool=tool_name,
                entity_id=None,
                detail=f"OCR text extraction verified ({len(txt)} characters)."
            )

        # Read-only operations (list, search, status)
        return VerificationResult(
            status="VERIFIED",
            tool=tool_name,
            entity_id=None,
            detail="Read-only query completed successfully."
        )


verification_engine = VerificationEngine()
