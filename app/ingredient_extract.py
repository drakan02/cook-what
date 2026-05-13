from typing import List
from app.llm_service import LLMServiceError, call_llm
from app.utils import parse_json_object
import re


def _fallback_extract_ingredients(user_message: str) -> List[str]:
    """Fallback ingredient extraction using regex patterns."""
    normalized = user_message.lower()
    candidate = user_message

    for prefix in [
        "tôi có",
        "mình có",
        "em có",
        "tui có",
        "nhà có",
        "nhà còn",
        "trong tủ còn",
        "tôi còn",
        "mình còn",
        "em còn",
    ]:
        if prefix in normalized:
            start = normalized.index(prefix) + len(prefix)
            candidate = user_message[start:]
            break

    candidate = re.split(r"\.\s*|\?\s*|!", candidate, maxsplit=1)[0]
    candidate = re.sub(
        r"\b(một|1)\s+(quả|cái|hộp|lon|miếng|ít)\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    parts = re.split(r",| và | với ", candidate)

    ingredients = []
    stop_words = ("không có", "không thể", "làm được", "làm món", "món gì")
    for part in parts:
        item = " ".join(part.strip(" .?;:").split())
        if not item or any(word in item.lower() for word in stop_words):
            continue
        ingredients.append(item)

    return ingredients


def extract_ingredients_from_text(user_message: str) -> List[str]:
    """Extract ingredients from user message using LLM.
    
    Args:
        user_message: User input text
        
    Returns:
        List of extracted ingredient strings
    """
    fallback_ingredients = _fallback_extract_ingredients(user_message)
    if len(fallback_ingredients) >= 2:
        return fallback_ingredients

    prompt = f"""
Trích xuất nguyên liệu thực phẩm từ câu người dùng.

Câu:
"{user_message}"

Chỉ trả JSON format:

{{
  "ingredients": ["..."]
}}

Nếu không có nguyên liệu thì trả:

{{
  "ingredients": []
}}
"""

    try:
        content = call_llm(prompt)
    except LLMServiceError:
        return fallback_ingredients

    parsed = parse_json_object(content)

    if isinstance(parsed, dict) and isinstance(parsed.get("ingredients"), list):
        return parsed["ingredients"]

    return fallback_ingredients
