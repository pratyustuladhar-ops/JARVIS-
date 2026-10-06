from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class VisionAnalysisRequest(BaseModel):
    image_data: str = Field(..., description="Base64 encoded image string or data URI")
    prompt: Optional[str] = Field(None, description="Specific query, instruction, or question about the image")
    mode: str = Field("screen_describe", description="Mode: screen_describe, ocr, explain, error_check, ui_elements")
    metadata: Optional[Dict[str, Any]] = None


class OCRResult(BaseModel):
    extracted_text: str = Field(..., description="Full text extracted from the visual buffer")
    lines: List[str] = Field(default_factory=list, description="Extracted lines of text")
    confidence: float = Field(0.95, description="OCR text recognition confidence score")
    language: str = Field("en", description="Detected language")


class UIElement(BaseModel):
    element_type: str = Field(..., description="button, text_field, icon, tab, window, menu")
    label: str = Field(..., description="Visible label or identifier")
    location_hint: Optional[str] = Field(None, description="e.g. top-right, center-bottom, toolbar")
    is_clickable: bool = True


class VisionAnalysisResponse(BaseModel):
    status: str = Field("success", description="success or failed")
    summary: str = Field(..., description="Comprehensive visual description or answer")
    detected_application: Optional[str] = Field(None, description="Active software application detected (e.g. VS Code, Chrome)")
    detected_elements: List[Dict[str, Any]] = Field(default_factory=list)
    ocr: Optional[OCRResult] = None
    error_detected: Optional[str] = None
    suggested_actions: List[str] = Field(default_factory=list)
    provider_used: str = Field("mock", description="Vision provider engine")
    duration_ms: float = 0.0
    verified: bool = True
    error: Optional[str] = None


class MultimodalInputMessage(BaseModel):
    type: str = Field("text", description="text, voice, image, or multimodal")
    content: Optional[str] = Field("", description="User command or prompt")
    image_data: Optional[str] = Field(None, description="Base64 encoded image data or data URI")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
