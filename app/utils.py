"""Shared utility functions."""

import json
import re
from typing import Any, Optional


def parse_json_object(value: Any) -> Optional[dict]:
    """Parse JSON object from string value or return dict directly."""
    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        pass

    match = re.search(r"\{.*\}", str(value), flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
