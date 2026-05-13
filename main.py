from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas import ChatRequest
from app.prompt_builder import build_prompt
from app.llm_service import call_llm_stream
from app.ingredient_extract import extract_ingredients_from_text
from app.intent_router import detect_intent

from src.vectordb import search

app = FastAPI(
    title="CookWhat API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary memory
conversation_memory = {}

@app.get("/")
def health():
    return {
        "status": "running",
        "message": "CookWhat API is running"
    }

def run_recipe_search(ingredients, top_k):
    query_text = ", ".join(ingredients)

    print(f"Searching vector DB: {query_text}")

    vector_results = search(
        query=query_text,
        n_results=top_k
    )

    return vector_results

def build_recipe_context(recipes):
    context = ""

    for i, recipe in enumerate(recipes, 1):
        context += f"""
Món {i}:
Tên món: {recipe.get('title')}
URL: {recipe.get('url')}
Thông tin:
{recipe.get('document')}
"""
    return context

@app.post("/chat")
def chat(request: ChatRequest):
    session_id = request.session_id or "default"
    user_message = request.message.strip()

    print("User message:", user_message)

    previous_context = conversation_memory.get(session_id)
    previous_ingredients = []

    if previous_context:
        previous_ingredients = previous_context.get("ingredients", [])

    intent_result = detect_intent(
        user_message=user_message,
        previous_ingredients=previous_ingredients
    )

    intent = intent_result.get("intent", "FOLLOW_UP")

    print("Detected intent:", intent)

    if intent == "NEW_SEARCH":
        ingredients = extract_ingredients_from_text(user_message)
        if not ingredients:
            return JSONResponse({
                "type": "error",
                "response": "Mình chưa nhận diện được nguyên liệu. Bạn thử nhập rõ hơn nhé."
            })

        vector_results = run_recipe_search(
            ingredients=ingredients,
            top_k=request.top_k
        )

        if not vector_results:
            return JSONResponse({
                "type": "no_result",
                "response": "Mình chưa tìm thấy món phù hợp."
            })

        conversation_memory[session_id] = {
            "ingredients": ingredients,
            "recipes": vector_results
        }

        prompt = build_prompt(
            user_ingredients=ingredients,
            vector_results=vector_results
        )
        return StreamingResponse(
            call_llm_stream(prompt),
            media_type="text/plain"
        )
    elif intent == "FOLLOW_UP":
        if not previous_context:
            return JSONResponse({
                "type": "missing_context",
                "response": "Mình chưa biết bạn đang có nguyên liệu gì. Hãy nhập nguyên liệu trước nhé."
            })

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

Nếu tất cả món không phù hợp:
hãy nói rõ lý do và đưa giải pháp thay thế.
"""
        return StreamingResponse(
            call_llm_stream(followup_prompt),
            media_type="text/plain"
        )
    elif intent == "RESEARCH":
        if not previous_context:
            return JSONResponse({
                "type": "missing_context",
                "response": "Hãy cho mình biết nguyên liệu bạn đang có trước nhé."
            })

        new_query = f"{', '.join(previous_ingredients)} {user_message}"

        print("Research query:", new_query)
        vector_results = search(
            query=new_query,
            n_results=request.top_k
        )

        if not vector_results:
            return JSONResponse({
                "type": "no_result",
                "response": "Mình chưa tìm thấy món phù hợp với yêu cầu mới này."
            })

        conversation_memory[session_id] = {
            "ingredients": previous_ingredients,
            "recipes": vector_results
        }

        prompt = build_prompt(
            user_ingredients=previous_ingredients,
            vector_results=vector_results
        )
        return StreamingResponse(
            call_llm_stream(prompt),
            media_type="text/plain"
        )

    elif intent == "ADD_INGREDIENT":
        if not previous_context:
            return JSONResponse({
                "type": "missing_context",
                "response": "Bạn chưa có nguyên liệu trước đó để mình cộng thêm."
            })

        new_ingredients = extract_ingredients_from_text(user_message)

        merged_ingredients = list(
            set(previous_ingredients + new_ingredients)
        )

        print("Merged ingredients:", merged_ingredients)

        vector_results = run_recipe_search(
            ingredients=merged_ingredients,
            top_k=request.top_k
        )

        if not vector_results:
            return JSONResponse({
                "type": "no_result",
                "response": "Mình chưa tìm thấy món phù hợp."
            })

        conversation_memory[session_id] = {
            "ingredients": merged_ingredients,
            "recipes": vector_results
        }

        prompt = build_prompt(
            user_ingredients=merged_ingredients,
            vector_results=vector_results
        )
        return StreamingResponse(
            call_llm_stream(prompt),
            media_type="text/plain"
        )
    elif intent == "SMALL_TALK":
        prompt = f"""
Bạn là CookWhat AI.

User nói:
"{user_message}"

Hãy trả lời thân thiện như chatbot.
Nếu user cảm ơn → đáp lại lịch sự.
Nếu user chào → chào lại.
"""
        return StreamingResponse(
            call_llm_stream(prompt),
            media_type="text/plain"
        )
    return JSONResponse({
        "type": "fallback",
        "response": "Mình chưa hiểu rõ yêu cầu của bạn. Bạn có thể nói rõ hơn không?"
    })