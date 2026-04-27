import requests
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_URL

def call_llm(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
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

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload
    )

    response.raise_for_status()

    data = response.json()

    return data["choices"][0]["message"]["content"]