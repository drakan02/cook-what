import logging
from typing import Any, Dict

import requests
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_URL

logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    pass


def _extract_error_detail(data: Any) -> str:
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return error.get("message") or error.get("code") or ""
    if isinstance(error, str):
        return error
    if isinstance(data, dict):
        return data.get("message") or data.get("detail") or ""
    return ""


def call_llm(prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        raise LLMServiceError("Thiếu OPENROUTER_API_KEY trong file .env.")
    if not OPENROUTER_MODEL:
        raise LLMServiceError("Thiếu OPENROUTER_MODEL trong file .env.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload: Dict[str, Any] = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.3,
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Failed to call OpenRouter")
        raise LLMServiceError(str(exc)) from exc

    try:
        data = response.json()
    except ValueError:
        snippet = response.text.strip().replace("\n", " ")[:180]
        detail = f"OpenRouter trả về phản hồi không phải JSON (HTTP {response.status_code})"
        if snippet:
            detail = f"{detail}: {snippet}"
        raise LLMServiceError(detail)

    if not response.ok:
        detail = _extract_error_detail(data) or f"HTTP {response.status_code}"
        raise LLMServiceError(detail)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMServiceError("OpenRouter trả về JSON không có nội dung trả lời.")

    if not content:
        raise LLMServiceError("Mô hình trả về nội dung rỗng.")

    return str(content)
