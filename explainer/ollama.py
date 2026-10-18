"""Call a local Ollama model. Uses only the standard library, and only the local server."""
from __future__ import annotations

import json
import os
import urllib.request

from explainer.prompt import SCHEMA, SYSTEM, user_message

DEFAULT_MODEL = "qwen3:4b"
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def chat(pack: dict, model: str = DEFAULT_MODEL, timeout: int = 900) -> dict:
    """Return the model's sentences, each with the fact ids it cites."""
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        # Ten sentences fit well inside this; the cap stops a repetition loop from running on.
        "options": {"temperature": 0, "seed": 1, "num_ctx": 8192, "num_predict": 2000},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(pack)}],
    }
    # Qwen3 thinks before answering unless told not to, which costs time and is not shown anyway.
    if model.startswith("qwen3"):
        body["think"] = False
    request = urllib.request.Request(f"{HOST}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        out = json.load(response)
    try:
        answer = json.loads(out["message"]["content"])
    except json.JSONDecodeError:
        # Output cut off by num_predict is not valid JSON; report it as an answer with no sentences.
        answer = {"sentences": [], "invalid_output": out["message"]["content"][-200:]}
    answer["model"] = model
    answer["seconds"] = round(out.get("total_duration", 0) / 1e9, 1)
    return answer
