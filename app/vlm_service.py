import base64
import logging
from typing import Any, Dict, Optional
import requests
from app.config import OPENROUTER_API_KEY, OPENROUTER_URL
from dotenv import load_dotenv
import os 

load_dotenv()

logger = logging.getLogger(__name__)

VLM_MODEL = os.getenv("OPENROUTER_VLM_MODEL")
_DEFAULT_SYSTEM_PROMPT = (
    "Bạn là trợ lý ẩm thực thông minh. "
    "Hãy mô tả chi tiết hình ảnh bằng tiếng Việt, "
    "tập trung vào các nguyên liệu thực phẩm, món ăn, "
    "hoặc đồ dùng bếp núc xuất hiện trong ảnh. "
    "Nếu có nguyên liệu, hãy liệt kê cụ thể từng loại."
)


class VLMServiceError(RuntimeError):
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


def _encode_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Return a data-URI string for the given image bytes."""
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def describe_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    user_query: Optional[str] = None,
) -> str:
    """Call the VLM API and return a text description of the image.

    Args:
        image_bytes: Raw bytes of the uploaded image.
        mime_type: MIME type of the image (e.g. ``"image/jpeg"``).
        user_query: Optional user question to guide the description.

    Returns:
        A string containing the VLM's description of the image.

    Raises:
        VLMServiceError: If the API call fails for any reason.
    """
    if not OPENROUTER_API_KEY:
        raise VLMServiceError("Thiếu OPENROUTER_API_KEY trong file .env.")

    data_uri = _encode_image(image_bytes, mime_type)

    # Build the user message with image + optional question
    text_part: str
    if user_query and user_query.strip():
        text_part = (
            f"Hãy mô tả hình ảnh này và trả lời câu hỏi sau: {user_query.strip()}"
        )
    else:
        text_part = "Hãy mô tả chi tiết hình ảnh này, đặc biệt là các nguyên liệu hoặc món ăn."

    payload: Dict[str, Any] = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": _DEFAULT_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                    {
                        "type": "text",
                        "text": text_part,
                    },
                ],
            },
        ],
        "temperature": 0.2,
        # "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Failed to call VLM via OpenRouter")
        raise VLMServiceError(str(exc)) from exc

    try:
        data = response.json()
    except ValueError:
        snippet = response.text.strip().replace("\n", " ")[:200]
        raise VLMServiceError(
            f"VLM trả về phản hồi không phải JSON (HTTP {response.status_code}): {snippet}"
        )

    if not response.ok:
        detail = _extract_error_detail(data) or f"HTTP {response.status_code}"
        raise VLMServiceError(detail)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise VLMServiceError("VLM trả về JSON không có nội dung trả lời.")

    if not content:
        raise VLMServiceError("VLM trả về nội dung rỗng.")

    return str(content).strip()
