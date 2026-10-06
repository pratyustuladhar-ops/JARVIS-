import os
import time
import shutil
import subprocess
import webbrowser
import logging
from typing import Dict, Any, Optional, List, Tuple

from local_agent.config import (
    APPLICATION_CANDIDATE_PATHS,
    APPLICATION_PROCESS_NAMES,
)
from local_agent.permissions import (
    validate_application,
    resolve_executable_path,
    validate_url,
    PermissionDeniedError
)

logger = logging.getLogger("jarvis.local_agent.tools.applications")


def is_process_running(process_names: List[str]) -> Tuple[bool, Optional[int]]:
    """
    Checks if any process matching expected names is currently active in the process table.
    Returns (is_running, pid).
    """
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name']):
            p_name = (p.info.get('name') or '').lower()
            for exp in process_names:
                if exp.lower() == p_name:
                    return True, p.info['pid']
    except Exception as e:
        logger.debug(f"Process check exception: {e}")
    return False, None


def focus_existing_window(pid: int) -> bool:
    """
    Attempts to safely bring an existing application window to focus.
    """
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        target_hwnd = None

        def enum_cb(hwnd, lparam):
            nonlocal target_hwnd
            w_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))
            if w_pid.value == pid and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    target_hwnd = hwnd
                    return False
            return True

        user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_cb), 0)
        if target_hwnd:
            user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(target_hwnd)
            return True
    except Exception:
        pass
    return False


def verify_application_launch(
    process_names: List[str],
    launched_pid: Optional[int] = None,
    max_retries: int = 5,
    retry_interval: float = 0.4
) -> Tuple[bool, Optional[int]]:
    """
    Real process verification:
    launch -> wait briefly -> check -> retry -> check again -> final result.
    Verifies that the expected application process is actively running in the Windows process table.
    """
    logger.info(f"Beginning process verification for {process_names} (initial PID: {launched_pid})")
    for attempt in range(1, max_retries + 1):
        time.sleep(retry_interval)

        # Check launched PID if still alive
        if launched_pid:
            try:
                import psutil
                if psutil.pid_exists(launched_pid):
                    p = psutil.Process(launched_pid)
                    p_name = p.name().lower()
                    if any(exp.lower() in p_name for exp in process_names):
                        logger.info(f"Verified process alive by PID {launched_pid} ({p_name}) on attempt {attempt}")
                        return True, launched_pid
            except Exception:
                pass

        # Check by expected process names (handles launcher stubs / child process handoffs)
        is_running, found_pid = is_process_running(process_names)
        if is_running:
            logger.info(f"Verified process alive by name matching {process_names} (PID: {found_pid}) on attempt {attempt}")
            return True, found_pid

        logger.debug(f"Verification attempt {attempt}/{max_retries} pending for {process_names}")

    logger.warning(f"Process verification failed for {process_names} after {max_retries} attempts.")
    return False, None


def open_application(application: str) -> Dict[str, Any]:
    """
    Safely launches an allowlisted Windows application with real process verification.
    Rejects arbitrary executables, shell commands, or unapproved software.
    """
    logger.info(f"Requested application: '{application}'")

    # 1. Validate application allowlist
    is_allowed, executable, error_msg = validate_application(application)
    if not is_allowed or not executable:
        logger.warning(f"Application validation rejected: '{application}' - {error_msg}")
        raise PermissionDeniedError(error_msg or f"Application '{application}' is not in the approved allowlist.")

    norm_app = application.lower().strip().rstrip(".?!,:;")
    logger.info(f"Normalized application: '{norm_app}', executable alias: '{executable}'")

    # 2. Resolve executable path
    resolved_path = resolve_executable_path(executable)
    path_exists = bool(resolved_path and os.path.isfile(resolved_path))
    logger.info(f"Resolved executable: '{resolved_path}', exists: {path_exists}")

    if not resolved_path or not path_exists:
        logger.warning(f"Executable for '{application}' not found on disk: {resolved_path}")
        return {
            "status": "failed",
            "success": False,
            "application": norm_app,
            "executable": executable,
            "resolved_path": None,
            "pid": None,
            "verified": False,
            "error_code": "APPLICATION_NOT_FOUND",
            "reason": "APPLICATION_NOT_FOUND",
            "error": f"Application '{application}' was not found on this system.",
            "message": f"Application '{application}' was not found on this system."
        }

    # 3. Check if already running
    expected_process_names = APPLICATION_PROCESS_NAMES.get(executable, [os.path.basename(resolved_path).lower()])
    already_running, existing_pid = is_process_running(expected_process_names)
    if already_running:
        logger.info(f"Application '{norm_app}' is already running (PID: {existing_pid}). Safe focus triggered.")
        focus_existing_window(existing_pid)
        return {
            "status": "success",
            "success": True,
            "application": norm_app,
            "executable": executable,
            "resolved_path": resolved_path,
            "pid": existing_pid,
            "already_running": True,
            "running": True,
            "verified": True,
            "message": f"{norm_app.title()} is already running."
        }

    # 4. Safe launch attempt
    try:
        startupinfo = subprocess.STARTUPINFO()
        if os.name == "nt":
            startupinfo.lpDesktop = r"WinSta0\Default"

        logger.info(f"Launching executable safely: '{resolved_path}'")
        # Handle .cmd files safely with cmd.exe /c if needed
        if resolved_path.lower().endswith(".cmd"):
            cmd_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
            proc = subprocess.Popen([cmd_exe, "/c", resolved_path], startupinfo=startupinfo, shell=False)
        else:
            proc = subprocess.Popen([resolved_path], startupinfo=startupinfo, shell=False)

        launched_pid = proc.pid
        logger.info(f"Process spawned with initial PID: {launched_pid}")

        # 5. Process Verification loop
        verified, confirmed_pid = verify_application_launch(
            process_names=expected_process_names,
            launched_pid=launched_pid,
            max_retries=5,
            retry_interval=0.4
        )

        final_pid = confirmed_pid or (launched_pid if verified else None)
        logger.info(f"Final verification result for '{norm_app}': verified={verified}, PID={final_pid}")

        if not verified:
            return {
                "status": "failed",
                "success": False,
                "application": norm_app,
                "executable": executable,
                "resolved_path": resolved_path,
                "pid": None,
                "verified": False,
                "error_code": "APPLICATION_LAUNCH_FAILED",
                "reason": "APPLICATION_LAUNCH_FAILED",
                "error": f"{norm_app.title()} could not be opened.",
                "message": f"{norm_app.title()} could not be opened."
            }

        return {
            "status": "success",
            "success": True,
            "application": norm_app,
            "executable": executable,
            "resolved_path": resolved_path,
            "pid": final_pid,
            "already_running": False,
            "running": True,
            "verified": True,
            "message": f"{norm_app.title()} launched successfully."
        }

    except Exception as e:
        logger.error(f"Launch exception for '{norm_app}': {e}")
        return {
            "status": "failed",
            "success": False,
            "application": norm_app,
            "executable": executable,
            "resolved_path": resolved_path,
            "pid": None,
            "verified": False,
            "error_code": "APPLICATION_LAUNCH_FAILED",
            "reason": "APPLICATION_LAUNCH_FAILED",
            "error": f"Failed to launch application '{application}': {e}",
            "message": f"{norm_app.title()} could not be opened."
        }


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
