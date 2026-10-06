import io
import time
import base64
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("jarvis.local_agent.screenshot")


def capture_screen(
    quality: int = 85,
    max_dimension: int = 1920,
    format_type: str = "PNG"
) -> Dict[str, Any]:
    """
    Safely captures the current Windows user screen.
    Only executed upon explicit user request or authorized agent step.
    Does NOT store screenshots permanently on disk without explicit instruction.
    Returns base64 encoded data URI.
    """
    try:
        from PIL import ImageGrab, Image
    except ImportError:
        logger.error("PIL (Pillow) is not available for screen capture.")
        return {
            "status": "failed",
            "reason": "DEPENDENCY_MISSING",
            "error": "Pillow imaging library is required for screen capture.",
            "verified": False
        }

    try:
        # In Windows background or sandboxed sessions, ensure thread is attached to the active desktop
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_desk = user32.OpenInputDesktop(0, False, 0x01FF)
            if not h_desk:
                h_desk = user32.OpenDesktopW('default', 0, False, 0x01FF)
            if h_desk:
                user32.SetThreadDesktop(h_desk)
        except Exception as e_desk:
            logger.debug(f"Desktop switch notice (non-fatal): {e_desk}")

        # Capture current Windows desktop screen
        img = ImageGrab.grab(all_screens=False)
        width, height = img.size

        # Scale down if exceeds max_dimension to preserve memory and token bandwidth
        if max(width, height) > max_dimension:
            scale = max_dimension / max(width, height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            width, height = new_w, new_h

        # Convert to RGB if format requires it (e.g. JPEG)
        if format_type.upper() in ["JPEG", "JPG"]:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

        buffer = io.BytesIO()
        save_format = "PNG" if format_type.upper() == "PNG" else "JPEG"
        if save_format == "JPEG":
            img.save(buffer, format=save_format, quality=quality, optimize=True)
            mime_type = "image/jpeg"
        else:
            img.save(buffer, format=save_format, optimize=True)
            mime_type = "image/png"

        buffer.seek(0)
        img_bytes = buffer.getvalue()
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_str}"

        return {
            "status": "success",
            "image_data": data_uri,
            "width": width,
            "height": height,
            "size_bytes": len(img_bytes),
            "mime_type": mime_type,
            "timestamp": datetime.utcnow().isoformat(),
            "verified": True,
            "message": f"Screen captured successfully ({width}x{height}, {len(img_bytes)} bytes)."
        }
    except Exception as e:
        err_msg = str(e)
        if "screen grab failed" in err_msg.lower():
            err_msg += " (Windows desktop session may be locked or running in a headless background service)"
        logger.error(f"Screen capture execution failed: {err_msg}")
        return {
            "status": "failed",
            "reason": "CAPTURE_FAILED",
            "error": f"Failed to capture screen: {err_msg}",
            "verified": False
        }
