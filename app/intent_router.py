from app.llm_service import call_llm
import json
import re


def _parse_json_object(value):
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


def _looks_like_new_search(message):
    normalized = message.lower()
    ingredient_markers = [
        "tôi có",
        "mình có",
        "em có",
        "tui có",
        "nhà có",
        "trong tủ",
        "còn",
        "nguyên liệu",
    ]
    return any(marker in normalized for marker in ingredient_markers) and (
        "," in message or " và " in normalized or " với " in normalized
    )


def _looks_like_small_talk(message):
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


def _looks_like_recipe_search(message):
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


def detect_intent(user_message, previous_ingredients=None):
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

    response = call_llm(prompt)
    parsed = _parse_json_object(response)

    if isinstance(parsed, dict) and parsed.get("intent"):
        return parsed

    return {"intent": "FOLLOW_UP"}
