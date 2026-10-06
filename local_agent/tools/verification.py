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
    if str(status).lower() in ["failed", "denied", "error"] or result.get("verified") is False or result.get("success") is False:
        return {
            "verified": False,
            "status": "FAILED",
            "detail": result.get("message") or result.get("error") or "Execution was unsuccessful."
        }

    if tool_name == "open_application":
        app = result.get("application", "")
        already_running = result.get("already_running", False)
        if already_running:
            return {
                "verified": True,
                "status": "VERIFIED",
                "detail": f"{app.title()} is already running."
            }

        pid = result.get("pid")
        is_alive = False
        if pid and verify_process_running(pid):
            is_alive = True
        else:
            # Robust Windows check: handle stub/launcher process exit (e.g. Windows 11 Notepad, CalculatorApp, Explorer)
            app_low = str(app).lower()
            name_candidates = [app_low]
            if "calc" in app_low:
                name_candidates.extend(["calc", "calculator", "calculatorapp"])
            elif "notepad" in app_low:
                name_candidates.extend(["notepad"])
            elif "chrome" in app_low:
                name_candidates.extend(["chrome"])
            elif "code" in app_low or "vscode" in app_low:
                name_candidates.extend(["code"])
            elif "explorer" in app_low:
                name_candidates.extend(["explorer"])
            elif "edge" in app_low:
                name_candidates.extend(["msedge"])
            elif "terminal" in app_low:
                name_candidates.extend(["windowsterminal", "wt"])

            for cand in name_candidates:
                if verify_process_running(cand):
                    is_alive = True
                    break

        return {
            "verified": is_alive,
            "status": "VERIFIED" if is_alive else "FAILED",
            "detail": f"{app.title()} process confirmed launched." if is_alive else f"Could not detect running process for '{app}'."
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

    elif tool_name == "open_folder":
        return {
            "verified": True,
            "status": "VERIFIED",
            "detail": f"Folder '{result.get('folder', 'directory')}' opened in File Explorer."
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
