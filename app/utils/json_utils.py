"""JSON parsing helpers for model outputs."""

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract first valid JSON object from model text output."""
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    code_fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_fence_match:
        return json.loads(code_fence_match.group(1))

    first_curly = text.find("{")
    last_curly = text.rfind("}")
    if first_curly != -1 and last_curly != -1 and first_curly < last_curly:
        return json.loads(text[first_curly : last_curly + 1])

    raise ValueError("No JSON object found in model response")
