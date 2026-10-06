import os
from typing import Dict, Set

# Backend connection settings
BACKEND_URL: str = os.getenv("JARVIS_BACKEND_URL", "http://localhost:8000/api/v1")
DEVICE_NAME: str = os.getenv("JARVIS_DEVICE_NAME", "JARVIS-WINDOWS-01")
PLATFORM: str = "Windows"
AGENT_VERSION: str = "1.0.0"
AUTH_TOKEN: str = os.getenv("JARVIS_LOCAL_AGENT_TOKEN", "jarvis_windows_local_agent_secret_2026")
HEARTBEAT_INTERVAL_SECONDS: int = 10

# Local execution bridge server
LOCAL_SERVER_HOST: str = "127.0.0.1"
LOCAL_SERVER_PORT: int = 8001

# Strict Application Allowlist (maps safe aliases to Windows executables)
# Arbitrary executable paths or shell commands are strictly forbidden.
ALLOWED_APPLICATIONS: Dict[str, str] = {
    "vscode": "code",
    "code": "code",
    "chrome": "chrome",
    "google-chrome": "chrome",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file-explorer": "explorer.exe",
    "edge": "msedge.exe",
    "msedge": "msedge.exe",
    "terminal": "wt.exe",
}

# Candidate standard install paths for allowlisted applications on Windows
APPLICATION_CANDIDATE_PATHS: Dict[str, list] = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome.exe",
        "chrome",
    ],
    "code": [
        "code",
        "code.cmd",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
    "notepad.exe": [
        "notepad.exe",
        r"C:\Windows\System32\notepad.exe",
        r"C:\Windows\notepad.exe",
    ],
    "calc.exe": [
        "calc.exe",
        r"C:\Windows\System32\calc.exe",
    ],
    "explorer.exe": [
        "explorer.exe",
        r"C:\Windows\explorer.exe",
    ],
    "msedge.exe": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "msedge.exe",
    ],
    "wt.exe": [
        "wt.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"),
    ],
}

# Strict Filesystem Directory Allowlist (resolves to user directory roots only)
# Traversal (..) and system directories (Windows, Program Files, AppData) are forbidden.
ALLOWED_DIRECTORIES: Dict[str, str] = {
    "desktop": os.path.realpath(os.path.expanduser("~/Desktop")),
    "documents": os.path.realpath(os.path.expanduser("~/Documents")),
    "downloads": os.path.realpath(os.path.expanduser("~/Downloads")),
}

# Permitted URL schemes (no file://, javascript:, data:)
ALLOWED_URL_SCHEMES: Set[str] = {"http", "https"}
