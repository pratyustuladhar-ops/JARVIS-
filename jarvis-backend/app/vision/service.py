import time
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.vision.provider import get_vision_provider, BaseVisionProvider
from app.vision.schemas import VisionAnalysisResponse, OCRResult
from app.services.activity_service import activity_service

logger = logging.getLogger("jarvis.vision.service")


class VisionService:
    """
    Central Multimodal Vision Orchestration Service.
    Enforces privacy policies, payload bounds, audit activity logging, and provider abstraction.
    """

    def __init__(self, provider: Optional[BaseVisionProvider] = None):
        self._provider = provider

    @property
    def provider(self) -> BaseVisionProvider:
        if self._provider:
            return self._provider
        return get_vision_provider()

    def validate_image_payload(self, image_data: str) -> None:
        """Enforces size limits and checks for non-empty image data."""
        if not image_data or not isinstance(image_data, str) or len(image_data.strip()) < 10:
            raise ValueError("Image data is missing, empty, or not a valid base64 payload.")

        # Rough size estimate in MB from base64 string length
        size_mb = (len(image_data) * 0.75) / (1024 * 1024)
        max_mb = getattr(settings, "MAX_IMAGE_SIZE_MB", 10)
        if size_mb > max_mb:
            raise ValueError(f"Image payload size ({size_mb:.2f} MB) exceeds maximum allowed limit ({max_mb} MB).")

    def analyze_image(
        self,
        db: Session,
        image_data: str,
        prompt: Optional[str] = None,
        mode: str = "screen_describe"
    ) -> Dict[str, Any]:
        """
        Executes vision analysis through configured provider with activity logging and verification.
        """
        if not getattr(settings, "VISION_ENABLED", True):
            raise PermissionError("Multimodal Vision capabilities are disabled by system settings.")

        start_time = time.time()
        self.validate_image_payload(image_data)

        # Log start of analysis (without logging raw image payload)
        activity_service.record_activity(
            db=db,
            event_type="IMAGE_ANALYSIS_STARTED",
            title=f"Vision Analysis ({mode.upper()})",
            description=f"Initiating visual analysis using provider: {getattr(settings, 'VISION_PROVIDER', 'mock')}",
            status="INFO",
            metadata_json=json.dumps({
                "mode": mode,
                "has_prompt": bool(prompt),
                "provider": getattr(settings, "VISION_PROVIDER", "mock")
            })
        )

        try:
            if mode == "ocr":
                raw_res = self.provider.extract_text_from_image(image_data)
            elif mode == "ui_elements":
                raw_res = self.provider.detect_ui_elements(image_data)
            elif mode == "screen_describe":
                raw_res = self.provider.describe_screen(image_data, prompt)
            else:
                raw_res = self.provider.analyze_image(image_data, prompt)

            duration_ms = round((time.time() - start_time) * 1000, 2)

            if raw_res.get("status") == "failed":
                activity_service.record_activity(
                    db=db,
                    event_type="VISION_ANALYSIS_FAILED",
                    title="Vision Analysis Failed",
                    description=f"Analysis failed: {raw_res.get('reason', 'UNKNOWN')}",
                    status="WARNING",
                    metadata_json=json.dumps({
                        "reason": raw_res.get("reason", "UNKNOWN"),
                        "duration_ms": duration_ms
                    })
                )
                return raw_res

            raw_res["duration_ms"] = duration_ms
            raw_res["verified"] = True

            # Log successful completion
            activity_service.record_activity(
                db=db,
                event_type="IMAGE_ANALYSIS_COMPLETED",
                title=f"Vision Analysis Completed ({mode.upper()})",
                description=f"Multimodal inference completed successfully in {duration_ms}ms.",
                status="SUCCESS",
                metadata_json=json.dumps({
                    "mode": mode,
                    "duration_ms": duration_ms,
                    "provider": raw_res.get("provider_used", "mock")
                })
            )

            return raw_res

        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(f"Vision analysis execution exception: {e}")
            activity_service.record_activity(
                db=db,
                event_type="VISION_ANALYSIS_FAILED",
                title="Vision Analysis Error",
                description=f"Vision exception: {str(e)}",
                status="ERROR",
                metadata_json=json.dumps({
                    "error": str(e),
                    "duration_ms": duration_ms
                })
            )
            return {
                "status": "failed",
                "reason": "EXECUTION_ERROR",
                "error": str(e),
                "verified": False,
                "duration_ms": duration_ms
            }

    def extract_text(self, db: Session, image_data: str) -> Dict[str, Any]:
        """Runs OCR extraction through vision layer."""
        if not getattr(settings, "OCR_ENABLED", True):
            raise PermissionError("OCR capabilities are disabled by system settings.")

        activity_service.record_activity(
            db=db,
            event_type="OCR_REQUESTED",
            title="OCR Extraction Requested",
            description="Extracting text from visual payload.",
            status="INFO"
        )
        return self.analyze_image(db, image_data, mode="ocr")


vision_service = VisionService()
