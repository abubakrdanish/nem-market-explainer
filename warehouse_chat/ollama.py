"""Ask the local Ollama model for a structured SQL decision."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from ingestion.config import WAREHOUSE_PATH
from warehouse_chat.prompt import SCHEMA, SYSTEM, user_message

DEFAULT_MODEL = "qwen3:4b"
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def ask(question: str, model: str = DEFAULT_MODEL, feedback: str | None = None,
        today: date | None = None, timeout: int = 120, warehouse: Path = WAREHOUSE_PATH) -> dict:
    """Return a query, refusal or clarification from the local model."""
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "seed": 1, "num_ctx": 16384, "num_predict": 600},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message(question, feedback, today, warehouse)},
        ],
    }
    if model.startswith("qwen3"):
        body["think"] = False
    request = urllib.request.Request(f"{HOST}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        out = json.load(response)
    content = out["message"]["content"]
    try:
        answer = json.loads(content)
    except json.JSONDecodeError:
        answer = {"kind": "invalid", "sql": "", "message": "The model did not return complete JSON.",
                  "caveats": [], "invalid_output": content[-200:]}
    answer["model"] = model
    answer["seconds"] = round(out.get("total_duration", 0) / 1e9, 1)
    return answer
