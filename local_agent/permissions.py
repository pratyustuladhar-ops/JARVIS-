import os
import re
from urllib.parse import urlparse
from typing import Tuple, Optional
import shutil
from local_agent.config import (
    AUTH_TOKEN,
    ALLOWED_APPLICATIONS,
    APPLICATION_CANDIDATE_PATHS,
    ALLOWED_DIRECTORIES,
    ALLOWED_URL_SCHEMES
)

# Risk Level Classification
LOW_RISK = "LOW_RISK"
MEDIUM_RISK = "MEDIUM_RISK"
HIGH_RISK = "HIGH_RISK"

TOOL_RISK_MAP = {
    "get_current_time": LOW_RISK,
    "get_system_info": LOW_RISK,
    "open_application": LOW_RISK,
    "open_url": LOW_RISK,
    "list_allowed_directory": MEDIUM_RISK,
    "open_file": MEDIUM_RISK,
    "open_folder": MEDIUM_RISK,
    "capture_screen": LOW_RISK,
}


def is_tool_allowed(tool_name: str) -> bool:
    """Checks if a tool is registered in the safe risk map."""
    return tool_name in TOOL_RISK_MAP


def validate_screen_capture(parameters: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """
    Validates screen capture permission.
    Allowed only on explicit user or tool action; continuous background capture is forbidden.
    Rejects any attempts to supply arbitrary file paths, commands, or continuous recording.
    """
    if parameters and ("output_path" in parameters or "file_path" in parameters or "cmd" in parameters or "path" in parameters):
        return False, "Arbitrary output paths or file writes for screen capture are strictly forbidden."
    return True, None



class PermissionDeniedError(Exception):
    pass


from local_agent.authentication import verify_agent_token

verify_auth_token = verify_agent_token


def validate_application(app_name: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates application name against strict allowlist.
    Returns: (is_allowed, resolved_executable, error_message)
    """
    if not app_name:
        return False, None, "Application name cannot be empty."

    norm = app_name.lower().strip()
    if norm in ALLOWED_APPLICATIONS:
        return True, ALLOWED_APPLICATIONS[norm], None

    # Handle cases like "code" for VS Code
    for alias, exe in ALLOWED_APPLICATIONS.items():
        if norm == alias or norm.replace(" ", "") == alias:
            return True, exe, None

    return False, None, f"Application '{app_name}' is not in the approved allowlist."


def resolve_executable_path(executable: str) -> Optional[str]:
    """
    Verifies that the configured executable exists on the Windows host.
    Checks system PATH and approved candidate standard install locations.
    Returns resolved path if found, or None if not installed (APPLICATION_NOT_FOUND).
    """
    if not executable:
        return None

    # Check direct executable or PATH
    found = shutil.which(executable)
    if found:
        return found

    # Check candidate paths for this allowlisted executable
    candidates = APPLICATION_CANDIDATE_PATHS.get(executable, [executable])
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
        found_cand = shutil.which(cand)
        if found_cand:
            return found_cand

    return None


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validates URL to prevent dangerous schemes and protocols.
    Only http and https are permitted.
    """
    if not url:
        return False, "URL cannot be empty."

    cleaned = url.strip()
    # Check if any scheme is present (e.g. javascript:, file:, data:, https:)
    has_scheme = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", cleaned))
    if not has_scheme:
        cleaned = "https://" + cleaned

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' is rejected. Only {ALLOWED_URL_SCHEMES} are permitted."

    if not parsed.netloc:
        return False, "Invalid URL hostname."

    return True, cleaned


def validate_directory_path(target: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates directory access strictly within Desktop, Documents, or Downloads.
    Rejects directory traversal (..) and access to system folders.
    """
    if not target:
        return False, None, "Directory target cannot be empty."

    norm = target.lower().strip().replace("/", "\\")

    # Direct alias match
    if norm in ALLOWED_DIRECTORIES:
        return True, ALLOWED_DIRECTORIES[norm], None

    # Check alias keywords
    for alias, base_path in ALLOWED_DIRECTORIES.items():
        if alias in norm:
            return True, base_path, None

    # Check if target is a path inside an allowed directory
    if ".." in target or "/" in target and ".." in target:
        return False, None, "Directory traversal (..) is strictly prohibited."

    try:
        resolved = os.path.realpath(target)
        for allowed_root in ALLOWED_DIRECTORIES.values():
            if os.path.exists(allowed_root):
                common = os.path.commonpath([resolved, allowed_root])
                if common == allowed_root:
                    return True, resolved, None
    except Exception as e:
        return False, None, f"Path resolution failed: {e}"

    return False, None, f"Directory '{target}' is outside approved user folders (Desktop, Documents, Downloads)."


def validate_file_path(file_path: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Ensures file resides inside an allowed directory.
    Rejects system files, executables (.exe/.bat/.cmd/.vbs), and path traversal.
    """
    if not file_path:
        return False, None, "File path cannot be empty."

    if ".." in file_path:
        return False, None, "Directory traversal (..) is prohibited."

    # Disallow opening executable files directly through this tool
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".exe", ".bat", ".cmd", ".vbs", ".ps1", ".msi", ".dll", ".reg"}:
        return False, None, f"Direct execution of '{ext}' files via open_file is blocked for security."

    # Handle natural query requesting "a file from downloads/desktop/documents"
    low_clean = file_path.lower().strip()
    target_dir_key = None
    if "download" in low_clean:
        target_dir_key = "downloads"
    elif "document" in low_clean:
        target_dir_key = "documents"
    elif "desktop" in low_clean:
        target_dir_key = "desktop"

    if target_dir_key and (low_clean in [f"a file from {target_dir_key}", f"file from {target_dir_key}", f"from {target_dir_key}", target_dir_key] or "a file from" in low_clean):
        dir_root = ALLOWED_DIRECTORIES.get(target_dir_key)
        if dir_root and os.path.exists(dir_root):
            for entry in os.listdir(dir_root):
                entry_path = os.path.join(dir_root, entry)
                entry_ext = os.path.splitext(entry)[1].lower()
                if os.path.isfile(entry_path) and entry_ext not in {".exe", ".bat", ".cmd", ".vbs", ".ps1", ".msi", ".dll", ".reg"}:
                    return True, entry_path, None

    # Check if file exists in any of the allowed directories by relative name
    for base_path in ALLOWED_DIRECTORIES.values():
        candidate = os.path.realpath(os.path.join(base_path, file_path))
        if os.path.commonpath([candidate, base_path]) == base_path and os.path.isfile(candidate):
            return True, candidate, None

    # If full path was provided, check if within allowed roots
    try:
        resolved = os.path.realpath(file_path)
        if os.path.isfile(resolved):
            for base_path in ALLOWED_DIRECTORIES.values():
                if os.path.commonpath([resolved, base_path]) == base_path:
                    return True, resolved, None
    except Exception:
        pass

    return False, None, f"File '{file_path}' was not found in approved user directories."


def validate_folder_path(folder_path: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates folder access strictly within Desktop, Documents, or Downloads.
    Rejects directory traversal (..) and access to system folders.
    """
    if not folder_path:
        return False, None, "Folder path cannot be empty."

    norm = folder_path.lower().strip().replace("/", "\\")

    if ".." in folder_path:
        return False, None, "Directory traversal (..) is prohibited."

    # Direct alias match (e.g. "desktop", "downloads", "documents")
    if norm in ALLOWED_DIRECTORIES:
        return True, ALLOWED_DIRECTORIES[norm], None

    for alias, base_path in ALLOWED_DIRECTORIES.items():
        if alias in norm and ("folder" in norm or "my " in norm or norm == alias):
            return True, base_path, None

    # Check if folder resides inside any allowed directory
    try:
        resolved = os.path.realpath(folder_path)
        if os.path.isdir(resolved):
            for base_path in ALLOWED_DIRECTORIES.values():
                if os.path.commonpath([resolved, base_path]) == base_path:
                    return True, resolved, None
    except Exception as e:
        return False, None, f"Path resolution failed: {e}"

    return False, None, f"Folder '{folder_path}' is outside approved user folders (Desktop, Documents, Downloads)."

