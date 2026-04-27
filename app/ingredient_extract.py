import requests
import json
import os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def extract_ingredients_from_text(user_message):
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
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload
    )

    result = response.json()

    content = result["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(content)
        return parsed["ingredients"]
    except:
        return []