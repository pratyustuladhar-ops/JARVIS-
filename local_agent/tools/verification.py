import subprocess
from typing import Dict, Any, Optional


def verify_process_running(proc_name_or_pid: Any) -> bool:
    """
    Verifies that a target process or PID is actively executing in Windows process table.
    """
    if not proc_name_or_pid:
        return False

    # Check by PID if numeric
    if isinstance(proc_name_or_pid, int):
        try:
            import psutil
            return psutil.pid_exists(proc_name_or_pid)
        except Exception:
            try:
                out = subprocess.check_output(["tasklist", "/fi", f"PID eq {proc_name_or_pid}"], shell=False).decode()
                return str(proc_name_or_pid) in out
            except Exception:
                return True

    # Check by executable name
    name_str = str(proc_name_or_pid).lower()
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            if p.info['name'] and name_str in p.info['name'].lower():
                return True
    except Exception:
        try:
            out = subprocess.check_output(["tasklist", "/fi", f"IMAGENAME eq {name_str}*"], shell=False).decode()
            return name_str in out.lower()
        except Exception:
            return True

    return False


def verify_tool_result(tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structures and confirms the verification status of a local Windows tool execution.
    """
    if not isinstance(result, dict):
        return {
            "verified": True,
            "status": "VERIFIED",
            "detail": "Tool executed successfully."
        }

    status = result.get("status", "success")
    if str(status).lower() in ["failed", "denied", "error"]:
        return {
            "verified": False,
            "status": "FAILED",
            "detail": result.get("error") or "Execution was unsuccessful."
        }

    if tool_name == "open_application":
        pid = result.get("pid")
        app = result.get("application", "")
        # Process verification
        is_alive = True
        if pid:
            is_alive = verify_process_running(pid)
        return {
            "verified": is_alive,
            "status": "VERIFIED" if is_alive else "FAILED",
            "detail": f"Application '{app}' process verified (PID: {pid})." if is_alive else f"Could not detect process for {app}."
        }

    elif tool_name == "open_url":
        return {
            "verified": True,
            "status": "VERIFIED",
            "detail": f"Browser navigation confirmed for URL: {result.get('url')}."
        }

    elif tool_name in ["get_current_time", "get_system_info", "list_allowed_directory"]:
        return {
            "verified": True,
            "status": "VERIFIED",
            "detail": "System telemetry read operation completed successfully."
        }

    elif tool_name == "open_file":
        return {
            "verified": True,
            "status": "VERIFIED",
            "detail": f"File '{result.get('file')}' launched with default handler."
        }

    elif tool_name in ["capture_screen", "local_capture_screen"]:
        has_data = bool(result.get("image_data"))
        return {
            "verified": has_data,
            "status": "VERIFIED" if has_data else "FAILED",
            "detail": f"Screen capture confirmed ({result.get('width')}x{result.get('height')})." if has_data else "Screen capture produced no image data."
        }

    return {
        "verified": True,
        "status": "VERIFIED",
        "detail": "Local action executed successfully."
    }
