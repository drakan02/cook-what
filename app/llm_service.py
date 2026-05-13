import json

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

def call_llm_stream(prompt):
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
        "temperature": 0.3,
        "stream": True
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        stream=True
    )

    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=False):
        if not line: continue
        line = line.decode("utf-8")
        if line.startswith(":"): continue
        if not line.startswith("data: "): continue
        data = line[6:]
        if data == "[DONE]": break

        try:
            json_data = json.loads(data)

            delta = (
                json_data
                .get("choices", [{}])[0]
                .get("delta", {})
                .get("content")
            )

            if delta:
                yield delta

        except Exception as e:
            print("Streaming parse error:", e)