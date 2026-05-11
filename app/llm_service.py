import requests
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_URL


def _llm_error_message(detail):
    if detail:
        return f"Mình đang gặp lỗi khi gọi mô hình AI: {detail}"
    return "Mình đang gặp lỗi khi gọi mô hình AI. Bạn thử gửi lại sau một lát nhé."


def _extract_error_detail(data):
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return error.get("message") or error.get("code")
    if isinstance(error, str):
        return error
    if isinstance(data, dict):
        return data.get("message") or data.get("detail")
    return None


def call_llm(prompt):
    if not OPENROUTER_API_KEY:
        return _llm_error_message("thiếu OPENROUTER_API_KEY trong file .env.")
    if not OPENROUTER_MODEL:
        return _llm_error_message("thiếu OPENROUTER_MODEL trong file .env.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        return _llm_error_message(str(exc))

    try:
        data = response.json()
    except ValueError:
        snippet = response.text.strip().replace("\n", " ")[:180]
        detail = f"OpenRouter trả về phản hồi không phải JSON (HTTP {response.status_code})"
        if snippet:
            detail = f"{detail}: {snippet}"
        return _llm_error_message(detail)

    if not response.ok:
        detail = _extract_error_detail(data) or f"HTTP {response.status_code}"
        return _llm_error_message(detail)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return _llm_error_message("OpenRouter trả về JSON không có nội dung trả lời.")

    if not content:
        return _llm_error_message("mô hình trả về nội dung rỗng.")

    return content
