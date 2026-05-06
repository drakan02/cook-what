from pydantic import BaseModel
from typing import Optional, List


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    top_k: int = 5


class ChatResponse(BaseModel):
    type: str
    session_id: str
    ingredients: Optional[List[str]] = None
    response: str


class TTSRequest(BaseModel):
    text: str
    lang: str = "vi"