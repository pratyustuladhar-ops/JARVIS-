import os
import time
import shutil
import subprocess
import webbrowser
from typing import Dict, Any

from local_agent.permissions import (
    validate_application,
    resolve_executable_path,
    validate_url,
    PermissionDeniedError
)


def open_application(application: str) -> Dict[str, Any]:
    """
    Safely launches an allowlisted Windows application.
    Rejects arbitrary executables, shell commands, or unapproved software.
    """
    is_allowed, executable, error_msg = validate_application(application)
    if not is_allowed or not executable:
        raise PermissionDeniedError(error_msg or f"Application '{application}' is not in the approved allowlist.")

    # Verify that the configured executable exists on the Windows host
    resolved_path = resolve_executable_path(executable)
    if not resolved_path:
        return {
            "status": "failed",
            "reason": "APPLICATION_NOT_FOUND",
            "application": application,
            "executable": executable,
            "verified": False,
            "error": f"Application '{application}' was not found on this system."
        }

    try:
        # Launch directly without shell injection vulnerability
        proc = subprocess.Popen([resolved_path], shell=False)
        time.sleep(0.3)
        is_running = proc.poll() is None

        return {
            "status": "success",
            "application": application,
            "executable": executable,
            "resolved_path": resolved_path,
            "pid": proc.pid,
            "running": is_running,
            "verified": True,
            "message": f"{application.title()} launched successfully."
        }
    except Exception as e:
        raise RuntimeError(f"Failed to launch application '{application}': {e}")


def open_url(url: str) -> Dict[str, Any]:
    """
    Opens an allowlisted web URL in the Windows default web browser.
    Rejects dangerous schemes like file://, javascript:, data:.
    """
    is_valid, validated_url = validate_url(url)
    if not is_valid or not validated_url:
        raise PermissionDeniedError(f"URL security validation rejected: {url}")

    try:
        opened = webbrowser.open(validated_url)
        return {
            "status": "success",
            "url": validated_url,
            "verified": bool(opened),
            "message": f"Opened {validated_url} in default browser."
        }
    except Exception as e:
        raise RuntimeError(f"Failed to open URL '{url}': {e}")
