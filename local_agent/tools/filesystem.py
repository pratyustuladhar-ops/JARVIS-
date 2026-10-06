import os
from datetime import datetime
from typing import Dict, Any, List

from local_agent.permissions import (
    validate_directory_path,
    validate_file_path,
    validate_folder_path,
    PermissionDeniedError
)


def list_allowed_directory(target_dir: str = "Desktop") -> Dict[str, Any]:
    """
    Safely lists directory contents within approved user folders (Desktop, Documents, Downloads).
    Rejects directory traversal (..) and access to system directories.
    """
    is_allowed, resolved_path, error_msg = validate_directory_path(target_dir)
    if not is_allowed or not resolved_path:
        raise PermissionDeniedError(error_msg or f"Access to directory '{target_dir}' is denied.")

    if not os.path.exists(resolved_path):
        return {
            "status": "success",
            "directory": os.path.basename(resolved_path),
            "path": resolved_path,
            "items": [],
            "total_items": 0,
            "message": "Directory exists but contains no accessible items."
        }

    items: List[Dict[str, Any]] = []
    try:
        with os.scandir(resolved_path) as entries:
            for entry in entries:
                if len(items) >= 40:
                    break
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "is_directory": entry.is_dir(),
                        "size_bytes": stat.st_size if entry.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    })
                except (PermissionError, FileNotFoundError):
                    continue

        return {
            "status": "success",
            "directory": os.path.basename(resolved_path),
            "path": resolved_path,
            "items": items,
            "total_items": len(items),
            "message": f"Retrieved {len(items)} items from {os.path.basename(resolved_path)}."
        }
    except Exception as e:
        raise RuntimeError(f"Failed listing directory: {e}")


def open_file(file_path: str) -> Dict[str, Any]:
    """
    Opens an approved document or media file residing inside an allowed directory using
    its default Windows program. Rejects executables and system paths.
    """
    is_allowed, safe_path, error_msg = validate_file_path(file_path)
    if not is_allowed or not safe_path:
        raise PermissionDeniedError(error_msg or f"Opening file '{file_path}' is denied.")

    try:
        os.startfile(safe_path)
        return {
            "status": "success",
            "file": os.path.basename(safe_path),
            "path": safe_path,
            "verified": True,
            "message": f"Opened '{os.path.basename(safe_path)}' with default Windows application."
        }
    except Exception as e:
        raise RuntimeError(f"Failed opening file '{file_path}': {e}")


def open_folder(folder_path: str = "Desktop") -> Dict[str, Any]:
    """
    Opens an approved directory (Desktop, Documents, Downloads) in Windows File Explorer.
    Rejects directory traversal (..) and access to system folders.
    """
    is_allowed, safe_path, error_msg = validate_folder_path(folder_path)
    if not is_allowed or not safe_path:
        raise PermissionDeniedError(error_msg or f"Opening folder '{folder_path}' is denied.")

    try:
        os.startfile(safe_path)
        return {
            "status": "success",
            "folder": os.path.basename(safe_path),
            "path": safe_path,
            "verified": True,
            "message": f"Opened folder '{os.path.basename(safe_path)}' in File Explorer."
        }
    except Exception as e:
        raise RuntimeError(f"Failed opening folder '{folder_path}': {e}")

