"""Utility functions for the ITL Control Plane Dashboard"""
from typing import Any, List, Union


def extract_name(resource_path: str) -> str:
    """Extract the short name from a full resource path.
    
    Example: /providers/ITL.Core/tenants/ITL -> ITL
    """
    if not resource_path:
        return ""
    return resource_path.rstrip("/").split("/")[-1]


def safe_list(data: Any) -> List[dict]:
    """Normalize API response to a list of resources.
    
    Handles various response formats:
    - Direct list: [...]
    - ARM style: {"value": [...]}
    - Legacy: {"resources": [...]} or {"items": [...]}
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # ARM style uses 'value', also support legacy 'resources'/'items'
        return data.get("value", data.get("resources", data.get("items", [])))
    return []


def format_uptime(seconds: int) -> str:
    """Format seconds into human-readable uptime string.
    
    Examples: "2d 5h", "3h 45m", "12m"
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    if hours > 24:
        return f"{hours // 24}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def mask_sensitive_value(key: str, value: str, sensitive_keys: set = None) -> str:
    """Mask sensitive values based on key name.
    
    Returns masked value if key contains sensitive words, otherwise original value.
    """
    if sensitive_keys is None:
        sensitive_keys = {"password", "secret", "key", "token", "credentials", "auth"}
    
    if any(s in key.lower() for s in sensitive_keys):
        return "••••••••"
    return value
