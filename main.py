import io
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from gtts import gTTS

from app import db
from app.ingredient_extract import extract_ingredients_from_text
from app.intent_router import detect_intent
from app.llm_service import call_llm
from app.prompt_builder import build_prompt
from app.schemas import ChatRequest, TTSRequest
from src.vectordb import search


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="CookWhat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Fallback memory when PostgreSQL is not configured or not reachable.
conversation_memory = {}
chat_history_memory = {}


@app.on_event("startup")
def startup():
    db.init_db()


def build_session_title(message):
    title = " ".join(message.strip().split())
    if not title:
        return "New chat"
    return title[:48] + ("..." if len(title) > 48 else "")


def remember_message(session_id, role, content, message_type=None, metadata=None):
    chat_history_memory.setdefault(session_id, []).append(
        {
            "role": role,
            "content": content,
            "message_type": message_type,
            "metadata": metadata or {},
        }
    )
    db.add_message(session_id, role, content, message_type, metadata)


def remember_context(session_id, ingredients, recipes):
    conversation_memory[session_id] = {"ingredients": ingredients, "recipes": recipes}
    db.set_session_context(session_id, ingredients, recipes)


def get_context(session_id):
    if session_id in conversation_memory:
        return conversation_memory[session_id]

    stored_context = db.get_session_context(session_id)
    if stored_context and stored_context.get("ingredients"):
        conversation_memory[session_id] = stored_context
        return stored_context

    return None


def chat_response(session_id, payload, message_type=None):
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
    """Chuyển văn bản thành giọng nói tiếng Việt, trả về MP3."""
    text = request.text.strip()
    if not text:
        return JSONResponse({"error": "Văn bản rỗng"}, status_code=400)

    try:
        tts = gTTS(text=text, lang=request.lang, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return StreamingResponse(
            fp,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/sessions")
def list_sessions():
    if db.ready():
        return db.list_sessions()

    return [
        {
            "id": session_id,
            "title": messages[0]["content"][:48] if messages else "New chat",
            "ingredients": conversation_memory.get(session_id, {}).get("ingredients", []),
        }
        for session_id, messages in chat_history_memory.items()
    ]


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    if db.ready():
        return db.get_messages(session_id)
    return chat_history_memory.get(session_id, [])


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    conversation_memory.pop(session_id, None)
    chat_history_memory.pop(session_id, None)
    db.delete_session(session_id)
    return {"status": "deleted"}


def run_recipe_search(ingredients, top_k):
    query_text = ", ".join(ingredients)

    print(f"Searching vector DB: {query_text}")

    vector_results = search(query=query_text, n_results=top_k)

    return vector_results


def build_recipe_context(recipes):
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


@app.post("/chat")
def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid4())
    user_message = request.message.strip()

    print("User message:", user_message)

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

    print("Detected intent:", intent)

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

        vector_results = run_recipe_search(ingredients=ingredients, top_k=request.top_k)

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

        prompt = build_prompt(user_ingredients=ingredients, vector_results=vector_results)

        llm_response = call_llm(prompt)

        return chat_response(
            session_id,
            {
                "type": "new_search",
                "session_id": session_id,
                "ingredients": ingredients,
                "response": llm_response,
            },
        )

    if intent == "FOLLOW_UP":
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

Nếu user hỏi:
- món nào healthy hơn
- món nào nhanh hơn
- món nào dễ hơn

=> chỉ phân tích trên danh sách món hiện có.

Nếu tất cả món không phù hợp:
hãy nói rõ lý do và đưa giải pháp thay thế.
"""
        llm_response = call_llm(followup_prompt)

        return chat_response(
            session_id,
            {
                "type": "follow_up",
                "session_id": session_id,
                "response": llm_response,
            },
        )

    if intent == "RESEARCH":
        if not previous_context:
            return chat_response(
                session_id,
                {
                    "type": "missing_context",
                    "session_id": session_id,
                    "response": "Hãy cho mình biết nguyên liệu bạn đang có trước nhé.",
                },
            )

        new_query = f"{', '.join(previous_ingredients)} {user_message}"

        print("Research query:", new_query)
        vector_results = search(query=new_query, n_results=request.top_k)

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

        prompt = build_prompt(
            user_ingredients=previous_ingredients,
            vector_results=vector_results,
        )

        llm_response = call_llm(prompt)

        return chat_response(
            session_id,
            {
                "type": "research",
                "session_id": session_id,
                "response": llm_response,
            },
        )

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
        merged_ingredients = list(set(previous_ingredients + new_ingredients))

        print("Merged ingredients:", merged_ingredients)

        vector_results = run_recipe_search(
            ingredients=merged_ingredients,
            top_k=request.top_k,
        )

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

        prompt = build_prompt(
            user_ingredients=merged_ingredients,
            vector_results=vector_results,
        )

        llm_response = call_llm(prompt)

        return chat_response(
            session_id,
            {
                "type": "add_ingredient",
                "session_id": session_id,
                "ingredients": merged_ingredients,
                "response": llm_response,
            },
        )

    if intent == "SMALL_TALK":
        prompt = f"""
Bạn là CookWhat AI.

User nói:
"{user_message}"

Hãy trả lời thân thiện như chatbot.
Nếu user cảm ơn thì đáp lại lịch sự.
Nếu user chào thì chào lại.
"""
        llm_response = call_llm(prompt)

        return chat_response(
            session_id,
            {
                "type": "small_talk",
                "session_id": session_id,
                "response": llm_response,
            },
        )

    return chat_response(
        session_id,
        {
            "type": "fallback",
            "session_id": session_id,
            "response": "Mình chưa hiểu rõ yêu cầu của bạn. Bạn có thể nói rõ hơn không?",
        },
    )
