from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    session_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=10)


class ChatResponse(BaseModel):
    type: str
    session_id: str
    ingredients: Optional[List[str]] = None
    response: str


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


class TTSRequest(BaseModel):
    text: str
    lang: str = "vi"
