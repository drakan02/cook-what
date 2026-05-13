from app.llm_service import LLMServiceError, call_llm
from app.utils import parse_json_object
from typing import Optional, Dict, List
import re


def _looks_like_new_search(message: str) -> bool:
    """Check if message looks like new ingredient search."""
    normalized = message.lower()
    ingredient_markers = [
        "tôi có",
        "mình có",
        "em có",
        "tui có",
        "nhà có",
        "nhà còn",
        "trong tủ",
        "trong tủ còn",
        "tôi còn",
        "mình còn",
        "em còn",
        "nguyên liệu",
    ]
    return any(marker in normalized for marker in ingredient_markers) and (
        "," in message or " và " in normalized or " với " in normalized
    )


def _looks_like_small_talk(message: str) -> bool:
    """Check if message is small talk."""
    normalized = message.lower().strip(" .!?")
    small_talk_phrases = {
        "hi",
        "hello",
        "hey",
        "xin chào",
        "chào",
        "chao",
        "cảm ơn",
        "cam on",
        "thanks",
        "thank you",
        "bye",
        "tạm biệt",
    }
    return normalized in small_talk_phrases


def _looks_like_recipe_search(message: str) -> bool:
    """Check if message is about recipe search."""
    normalized = message.lower()
    recipe_markers = [
        "tôi muốn làm",
        "mình muốn làm",
        "muốn làm món",
        "làm món",
        "nấu món",
        "cách làm",
        "công thức",
        "recipe",
    ]
    return any(marker in normalized for marker in recipe_markers)


def detect_intent(user_message: str, previous_ingredients: Optional[List[str]] = None) -> Dict[str, str]:
    """Detect user intent from message.
    
    Args:
        user_message: User input text
        previous_ingredients: List of ingredients from previous context
        
    Returns:
        Dict with 'intent' key containing intent type
    """
    if _looks_like_small_talk(user_message):
        return {"intent": "SMALL_TALK"}

    if _looks_like_new_search(user_message):
        return {"intent": "NEW_SEARCH"}

    if _looks_like_recipe_search(user_message):
        return {"intent": "RESEARCH"}

    prompt = f"""
Bạn là intent classifier cho ứng dụng gợi ý món ăn.

User message:
"{user_message}"

Nguyên liệu trước đó:
{previous_ingredients}

Phân loại message vào đúng 1 loại:

1. NEW_SEARCH
→ user đang nhập nguyên liệu mới

Ví dụ:
- tôi có gà, trứng
- trong tủ còn thịt bò


2. FOLLOW_UP
→ user đang hỏi thêm về các món đã gợi ý

Ví dụ:
- món nào nhanh hơn
- món nào healthy nhất trong các món trên
- món nào ngon nhất


3. RESEARCH
→ user muốn món khác hoàn toàn / đổi style món

Ví dụ:
- món khác đi
- món nhật
- món hàn
- món hấp
- món chay
- món ít calo
- đang giảm cân, muốn ăn món healthy hơn


4. ADD_INGREDIENT
→ user thêm nguyên liệu mới

Ví dụ:
- tôi có thêm trứng
- thêm nấm nữa


5. SMALL_TALK
→ cảm ơn, hello, bye...

Trả về JSON:

{{
    "intent": ""
}}
"""

    try:
        response = call_llm(prompt)
    except LLMServiceError:
        return {"intent": "FOLLOW_UP"}

    parsed = parse_json_object(response)

    if isinstance(parsed, dict) and parsed.get("intent"):
        return parsed

    return {"intent": "FOLLOW_UP"}
