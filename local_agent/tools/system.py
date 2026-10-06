import os
import time
import platform
from datetime import datetime
from typing import Dict, Any

from local_agent.config import AGENT_VERSION, DEVICE_NAME


def get_current_time() -> Dict[str, Any]:
    """
    Returns the current local system time on Windows.
    Safe read-only operation.
    """
    now = datetime.now()
    tz_name = time.tzname[time.daylight] if time.daylight else time.tzname[0]
    return {
        "status": "success",
        "formatted": now.strftime("%A, %B %d, %Y - %I:%M:%S %p"),
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": tz_name,
        "platform": "Windows"
    }


def get_system_info() -> Dict[str, Any]:
    """
    Returns safe, non-sensitive Windows operating system telemetry.
    Strictly excludes credentials, keys, browser cookies, and personal files.
    """
    # Memory metrics via psutil if present or standard fallback
    ram_total_gb = "Unknown"
    ram_available_gb = "Unknown"
    cpu_percent = 0.0

    try:
        import psutil
        mem = psutil.virtual_memory()
        ram_total_gb = f"{mem.total / (1024 ** 3):.1f} GB"
        ram_available_gb = f"{mem.available / (1024 ** 3):.1f} GB"
        cpu_percent = psutil.cpu_percent(interval=0.1)
    except Exception:
        pass

    return {
        "status": "success",
        "device_name": DEVICE_NAME,
        "agent_version": AGENT_VERSION,
        "os": f"{platform.system()} {platform.release()} (Build {platform.version()})",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count() or 1,
        "cpu_usage_percent": cpu_percent,
        "ram_total": ram_total_gb,
        "ram_available": ram_available_gb,
        "python_version": platform.python_version()
    }
