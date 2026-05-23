import io
import re
import logging
import os
import sys
import traceback
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from piper import PiperVoice
from piper.config import SynthesisConfig

from app import db
from app.config import validate_config
from app.prompt_builder import build_prompt
from app.llm_service import call_llm_stream
from app.ingredient_extract import extract_ingredients_from_text
from app.intent_router import detect_intent
from app.nutrition_service import lookup_many
from app.schemas import ChatRequest, SessionUpdateRequest, TTSRequest
from app.vlm_service import VLMServiceError, describe_image
from src.vectordb import search

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="CookWhat API", version="1.0.0")

# Allow specific origins for CORS security
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Fallback memory when PostgreSQL is not configured or not reachable.
conversation_memory = {}
chat_history_memory = {}
session_meta_memory = {}


BASE_PIPER_MODEL = BASE_DIR / "models" / "tts" / "vi_VN-vais1000-medium.onnx"
piper_voice: Optional[PiperVoice] = None


class RecipeSearchError(RuntimeError):
    pass


@app.on_event("startup")
def startup() -> None:
    """Initialize app on startup: validate config, init DB, load TTS model."""
    global piper_voice
    
    # Validate configuration
    validate_config()
    
    # Initialize database
    db.init_db()
    
    # Load TTS model
    if BASE_PIPER_MODEL.exists():
        logger.info("Loading Piper voice model...")
        piper_voice = PiperVoice.load(str(BASE_PIPER_MODEL))
        logger.info("Piper model loaded successfully")
    else:
        logger.warning(f"Piper model not found at {BASE_PIPER_MODEL}")
    
    logger.info("Application startup complete")


def build_session_title(message: str) -> str:
    """Build session title from first user message (max 48 chars)."""
    title = " ".join(message.strip().split())
    if not title:
        return "New chat"
    return title[:48] + ("..." if len(title) > 48 else "")


def debug_log(label: str, value: Any) -> None:
    """Log debug info with proper encoding."""
    safe_value = str(value).encode("unicode_escape").decode("ascii")
    logger.debug(f"{label}: {safe_value}")


def get_session_meta(session_id: str) -> Dict[str, Any]:
    """Get or create session metadata."""
    return session_meta_memory.setdefault(
        session_id,
        {"title": "New chat", "pinned": False},
    )


def peek_session_meta(session_id):
    return session_meta_memory.get(session_id, {})


def set_session_meta(session_id: str, title: Optional[str] = None, pinned: Optional[bool] = None) -> Dict[str, Any]:
    """Update session metadata."""
    meta = get_session_meta(session_id)
    if title is not None:
        meta["title"] = title
    if pinned is not None:
        meta["pinned"] = pinned
    return meta


def remember_message(session_id: str, role: str, content: str, message_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Remember message in memory and DB."""
    chat_history_memory.setdefault(session_id, []).append(
        {
            "role": role,
            "content": content,
            "message_type": message_type,
            "metadata": metadata or {},
        }
    )
    db.add_message(session_id, role, content, message_type, metadata)


def remember_context(session_id: str, ingredients: List[str], recipes: List[Dict[str, Any]]) -> None:
    """Remember recipe context in memory and DB."""
    conversation_memory[session_id] = {"ingredients": ingredients, "recipes": recipes}
    db.set_session_context(session_id, ingredients, recipes)


def get_context(session_id: str) -> Optional[Dict[str, Any]]:
    """Get recipe context for session from memory or DB."""
    if session_id in conversation_memory:
        return conversation_memory[session_id]

    stored_context = db.get_session_context(session_id)
    if stored_context and stored_context.get("ingredients"):
        conversation_memory[session_id] = stored_context
        return stored_context

    return None


def chat_response(session_id: str, payload: Dict[str, Any], message_type: Optional[str] = None) -> JSONResponse:
    """Send chat response and remember message."""
    response_text = payload.get("response")
    if response_text:
        remember_message(
            session_id,
            "assistant",
            response_text,
            message_type or payload.get("type"),
            payload,
        )
    return JSONResponse(payload)


def stream_chat_response(session_id: str, stream, message_type: str = "assistant") -> StreamingResponse:
    """Stream plain text to client and persist full assistant reply after completion."""
    def iterator():
        chunks: List[str] = []

        try:
            for chunk in stream:
                if not chunk:
                    continue
                chunks.append(chunk)
                yield chunk
        except Exception as exc:
            logger.exception("Streaming chat response failed: %s", exc)
            error_message = f"\n\nMình đang gặp lỗi khi gọi mô hình AI: {exc}"
            chunks.append(error_message)
            yield error_message
        finally:
            full_response = "".join(chunks).strip()
            if full_response:
                remember_message(session_id, "assistant", full_response, message_type)

    return StreamingResponse(
        iterator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Session-Id": session_id},
    )


def llm_error_response(session_id: str, exc: Exception) -> JSONResponse:
    """Handle LLM errors."""
    logger.error(f"LLM error: {exc}")
    return chat_response(
        session_id,
        {
            "type": "llm_error",
            "session_id": session_id,
            "response": f"Mình đang gặp lỗi khi gọi mô hình AI: {exc}",
        },
    )


def search_error_response(session_id: str, exc: Exception) -> JSONResponse:
    """Handle recipe search errors."""
    logger.error(f"Search error: {exc}")
    return chat_response(
        session_id,
        {
            "type": "search_error",
            "session_id": session_id,
            "response": f"Mình đang gặp lỗi khi tìm công thức: {exc}",
        },
    )


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {
        "status": "running",
        "message": "CookWhat API is running",
        "postgres_history": db.ready(),
    }


@app.post("/api/tts")
def text_to_speech(request: TTSRequest):
    """Chuyển văn bản thành giọng nói tiếng Việt bằng Piper TTS (local), trả về WAV."""
    text = request.text.strip()
    if not text:
        return JSONResponse({"error": "Văn bản rỗng"}, status_code=400)
    if piper_voice is None:
        return JSONResponse(
            {"error": "TTS model chưa được load. Kiểm tra file model tại models/tts/"},
            status_code=503,
        )

    # Khoảng lặng giữa các câu (giây) — điều chỉnh tùy ý
    SENTENCE_SILENCE_SEC = 0.45   # sau dấu . ! ?
    COMMA_SILENCE_SEC    = 0.20   # sau dấu ,

    try:
        syn_config = SynthesisConfig(length_scale=1.3)

        sample_rate = sample_width = sample_channels = None
        all_frames = bytearray()

        # Tách text thành các đoạn con theo dấu phẩy/chấm để kiểm soát pause
        segments = re.split(r'([,،])', text)
        # Ghép lại segment + dấu phẩy kề
        merged: list[str] = []
        i = 0
        while i < len(segments):
            part = segments[i]
            if i + 1 < len(segments) and segments[i + 1] in (',', '،'):
                merged.append(part + segments[i + 1])
                i += 2
            else:
                if part.strip():
                    merged.append(part)
                i += 1

        for seg_idx, segment in enumerate(merged):
            seg_text = segment.strip()
            if not seg_text:
                continue

            is_comma_end = seg_text.endswith((',', '،'))

            for chunk in piper_voice.synthesize(seg_text, syn_config=syn_config):
                if sample_rate is None:
                    sample_rate    = chunk.sample_rate
                    sample_width   = chunk.sample_width
                    sample_channels = chunk.sample_channels

                all_frames.extend(chunk.audio_int16_bytes)

                # Thêm silence sau mỗi câu (dấu . ! ? được phonemizer xử lý)
                silence_sec = COMMA_SILENCE_SEC if is_comma_end else SENTENCE_SILENCE_SEC
                n_silence_bytes = int(sample_rate * silence_sec) * sample_width * sample_channels
                all_frames.extend(bytes(n_silence_bytes))

        if sample_rate is None:
            return JSONResponse({"error": "Không có audio được tạo"}, status_code=500)

        fp = io.BytesIO()
        with wave.open(fp, "wb") as wav_file:
            wav_file.setnchannels(sample_channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(all_frames))
        fp.seek(0)
        return StreamingResponse(
            fp,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/analyze-image")
async def analyze_image(
    image: UploadFile = File(...),
    query: str = Form(default=""),
):
    """Preprocess layer: convert an uploaded image to descriptive text via VLM.

    The frontend sends the image (and an optional user question) here.
    The returned ``description`` is prepended to the user's chat message before it reaches the core chatbot pipeline.
    """
    # Validate content-type loosely
    content_type = (image.content_type or "").lower()
    if not content_type.startswith("image/"):
        return JSONResponse(
            {"error": "File tải lên phải là hình ảnh (JPEG, PNG, WEBP, …)"},
            status_code=400,
        )

    # Cap file size at 10 MB to avoid abusing the API
    MAX_BYTES = 10 * 1024 * 1024
    image_bytes = await image.read()
    if len(image_bytes) > MAX_BYTES:
        return JSONResponse(
            {"error": "Hình ảnh quá lớn. Vui lòng chọn ảnh dưới 10 MB."},
            status_code=413,
        )

    try:
        description = describe_image(
            image_bytes=image_bytes,
            mime_type=content_type or "image/jpeg",
            user_query=query or None,
        )
    except VLMServiceError as exc:
        logger.error(f"VLM error: {exc}")
        return JSONResponse(
            {"error": f"Không thể phân tích ảnh: {exc}"},
            status_code=502,
        )

    return JSONResponse({"description": description})


@app.get("/api/sessions")
def list_sessions():
    if db.ready():
        return db.list_sessions()

    sessions = [
        {
            "id": session_id,
            "title": peek_session_meta(session_id).get("title", messages[0]["content"][:48] if messages else "New chat"),
            "pinned": peek_session_meta(session_id).get("pinned", False),
            "ingredients": conversation_memory.get(session_id, {}).get("ingredients", []),
        }
        for session_id, messages in chat_history_memory.items()
    ]

    return sorted(sessions, key=lambda session: (not session.get("pinned", False),))


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    if db.ready():
        return db.get_messages(session_id)
    return chat_history_memory.get(session_id, [])


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    conversation_memory.pop(session_id, None)
    chat_history_memory.pop(session_id, None)
    session_meta_memory.pop(session_id, None)
    db.delete_session(session_id)
    return {"status": "deleted"}


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: str, request: SessionUpdateRequest):
    title = request.title.strip() if request.title is not None else None
    if title == "":
        title = "New chat"

    updated = False

    if db.ready():
        updated = db.update_session(session_id, title=title, pinned=request.pinned)

    if session_id in chat_history_memory or session_id in conversation_memory or session_id in session_meta_memory:
        set_session_meta(session_id, title=title, pinned=request.pinned)
        if title is not None:
            updated = True

    if not updated and not db.ready():
        return {"status": "not_found"}

    return {
        "status": "updated",
        "session": {
            "id": session_id,
            "title": get_session_meta(session_id).get("title", "New chat"),
            "pinned": get_session_meta(session_id).get("pinned", False),
        },
    }


def run_recipe_search(ingredients: List[str], top_k: int) -> List[Dict[str, Any]]:
    """Search for recipes by ingredients."""
    query_text = ", ".join(ingredients)

    debug_log("Searching vector DB", query_text)

    try:
        vector_results = search(query=query_text, n_results=top_k)
    except Exception as exc:
        raise RecipeSearchError(str(exc)) from exc

    return vector_results


def build_recipe_context(recipes: List[Dict[str, Any]]) -> str:
    """Build formatted recipe context for LLM."""
    context = ""

    for i, recipe in enumerate(recipes, 1):
        context += f"""
Mon {i}:
Ten mon: {recipe.get('title')}
URL: {recipe.get('url')}
Thong tin:
{recipe.get('document')}
"""
    return context


def get_nutrition_context(ingredients: List[str], recipes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get nutrition info for ingredients and recipes."""
    queries = list(ingredients)
    queries.extend(recipe.get("title", "") for recipe in recipes if recipe.get("title"))
    return lookup_many(queries)


@app.post("/chat")
def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid4())
    user_message = request.message.strip()

    debug_log("User message", user_message)

    if not db.ready():
        set_session_meta(session_id, title=build_session_title(user_message))
    db.upsert_session(session_id, title=build_session_title(user_message))
    remember_message(session_id, "user", user_message)

    previous_context = get_context(session_id)
    previous_ingredients = []

    if previous_context:
        previous_ingredients = previous_context.get("ingredients", [])

    intent_result = detect_intent(
        user_message=user_message,
        previous_ingredients=previous_ingredients,
    )

    intent = intent_result.get("intent", "FOLLOW_UP")

    debug_log("Detected intent", intent)

    if intent == "NEW_SEARCH":
        ingredients = extract_ingredients_from_text(user_message)
        if not ingredients:
            return chat_response(
                session_id,
                {
                    "type": "error",
                    "session_id": session_id,
                    "response": "Mình chưa nhận diện được nguyên liệu. Bạn thử nhập rõ hơn nhé.",
                },
            )

        try:
            vector_results = run_recipe_search(ingredients=ingredients, top_k=request.top_k)
        except RecipeSearchError as exc:
            return search_error_response(session_id, exc)

        if not vector_results:
            return chat_response(
                session_id,
                {
                    "type": "no_result",
                    "session_id": session_id,
                    "response": "Mình chưa tìm thấy món phù hợp.",
                },
            )

        remember_context(session_id, ingredients, vector_results)
        nutrition_context = get_nutrition_context(ingredients, vector_results)

        prompt = build_prompt(
            user_ingredients=ingredients,
            vector_results=vector_results,
            user_request=user_message,
            nutrition_context=nutrition_context,
        )
        return stream_chat_response(session_id, call_llm_stream(prompt), "recipe_search")
    elif intent == "FOLLOW_UP":
        if not previous_context:
            return chat_response(
                session_id,
                {
                    "type": "missing_context",
                    "session_id": session_id,
                    "response": "Mình chưa biết bạn đang có nguyên liệu gì. Hãy nhập nguyên liệu trước nhé.",
                },
            )

        previous_recipes = previous_context["recipes"]
        recipe_context = build_recipe_context(previous_recipes)

        followup_prompt = f"""
Bạn là CookWhat AI.

Người dùng hiện có nguyên liệu:
{", ".join(previous_ingredients)}

Các món đã gợi ý:
{recipe_context}

User hỏi tiếp:
"{user_message}"

Hãy trả lời tự nhiên như ChatGPT bằng tiếng Việt.
Khi nhắc tới món nào:
- luôn ghi rõ tên món
- luôn kèm Link công thức của món đó
- có xuống dòng 
- có bullet points

Ví dụ:
- Gà chiên nước mắm
Link công thức: https://...

- Gà hấp gừng
Link công thức: https://...

Nếu user hỏi:
- món nào healthy hơn
- món nào nhanh hơn
- món nào dễ hơn

=> chỉ phân tích trên danh sách món hiện có.

Nếu user hỏi sâu về dinh dưỡng/calo/macro/protein/chất béo/carb của một món cụ thể:
- trả lời tập trung vào món đó
- ước lượng các nutrient quan trọng: calo, protein, chất béo, carb, chất xơ, đường, sodium nếu có thể
- nói rõ đây là ước lượng nếu công thức không có định lượng chính xác

Nếu tất cả món không phù hợp:
hãy nói rõ lý do và đưa giải pháp thay thế.
"""
        return stream_chat_response(session_id, call_llm_stream(followup_prompt), "follow_up")
    elif intent == "RESEARCH":
        if not previous_context:
            debug_log("Recipe search query", user_message)
            try:
                vector_results = search(query=user_message, n_results=request.top_k)
            except Exception as exc:
                return search_error_response(session_id, exc)

            if not vector_results:
                return chat_response(
                    session_id,
                    {
                        "type": "no_result",
                        "session_id": session_id,
                        "response": "Mình chưa tìm thấy công thức phù hợp với yêu cầu này.",
                    },
                )

            ingredients = [user_message]
            remember_context(session_id, ingredients, vector_results)
            nutrition_context = get_nutrition_context(ingredients, vector_results)

            prompt = build_prompt(
                user_ingredients=ingredients,
                vector_results=vector_results,
                user_request=user_message,
                nutrition_context=nutrition_context,
            )

            return stream_chat_response(session_id, call_llm_stream(prompt), "recipe_search")

        new_query = f"{', '.join(previous_ingredients)} {user_message}"

        debug_log("Research query", new_query)
        try:
            vector_results = search(query=new_query, n_results=request.top_k)
        except Exception as exc:
            return search_error_response(session_id, exc)

        if not vector_results:
            return chat_response(
                session_id,
                {
                    "type": "no_result",
                    "session_id": session_id,
                    "response": "Mình chưa tìm thấy món phù hợp với yêu cầu mới này.",
                },
            )

        remember_context(session_id, previous_ingredients, vector_results)
        nutrition_context = get_nutrition_context(previous_ingredients, vector_results)

        prompt = build_prompt(
            user_ingredients=previous_ingredients,
            vector_results=vector_results,
            user_request=user_message,
            nutrition_context=nutrition_context,
        )
        return stream_chat_response(session_id, call_llm_stream(prompt), "recipe_search")

    if intent == "ADD_INGREDIENT":
        if not previous_context:
            return chat_response(
                session_id,
                {
                    "type": "missing_context",
                    "session_id": session_id,
                    "response": "Bạn chưa có nguyên liệu trước đó để mình cộng thêm.",
                },
            )

        new_ingredients = extract_ingredients_from_text(user_message)
        merged_ingredients = list(dict.fromkeys(previous_ingredients + new_ingredients))

        debug_log("Merged ingredients", merged_ingredients)

        try:
            vector_results = run_recipe_search(
                ingredients=merged_ingredients,
                top_k=request.top_k,
            )
        except RecipeSearchError as exc:
            return search_error_response(session_id, exc)

        if not vector_results:
            return chat_response(
                session_id,
                {
                    "type": "no_result",
                    "session_id": session_id,
                    "response": "Mình chưa tìm thấy món phù hợp.",
                },
            )

        remember_context(session_id, merged_ingredients, vector_results)
        nutrition_context = get_nutrition_context(merged_ingredients, vector_results)

        prompt = build_prompt(
            user_ingredients=merged_ingredients,
            vector_results=vector_results,
            user_request=user_message,
            nutrition_context=nutrition_context,
        )
        return stream_chat_response(session_id, call_llm_stream(prompt), "recipe_search")
    elif intent == "SMALL_TALK":
        prompt = f"""
Bạn là CookWhat AI.

User nói:
"{user_message}"

Hãy trả lời thân thiện như chatbot.
Nếu user cảm ơn thì đáp lại lịch sự.
Nếu user chào thì chào lại.
"""
        return stream_chat_response(session_id, call_llm_stream(prompt), "small_talk")
    return JSONResponse({
        "type": "fallback",
        "response": "Mình chưa hiểu rõ yêu cầu của bạn. Bạn có thể nói rõ hơn không?"
    })
