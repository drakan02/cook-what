from app.llm_service import call_llm
import json

def detect_intent(user_message, previous_ingredients=None):
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

    try:
        return json.loads(response)
    except:
        return {"intent": "FOLLOW_UP"}