import json
import re
from groq import Groq
from app.config import settings

_client = None


def client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def call(system: str, user: str, max_tokens: int = 1000) -> str:
    resp = client().chat.completions.create(
        model=settings.groq_model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # qwen3 on Groq is a reasoning model; turning reasoning off keeps the
        # reply itself clean (no hidden chain-of-thought) and faster/cheaper.
        # If Groq renames/removes this param for the pinned model, this is
        # silently ignored by extra_body rather than erroring.
        extra_body={"reasoning_effort": "none"},
    )
    return resp.choices[0].message.content or ""


def call_json(system: str, user: str, max_tokens: int = 1000):
    """Call the model and parse the reply as JSON, tolerating stray markdown fences
    or a leading sentence the model adds despite being told not to."""
    text = call(system + " Respond ONLY with raw JSON. No markdown fences, no commentary.", user, max_tokens)
    cleaned = re.sub(r"```json|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min([i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1], default=-1)
        if start == -1:
            raise
        return json.loads(cleaned[start:])


def transcribe_audio(file_path: str, language: str = "zh"):
    """Send an audio file to Groq's hosted Whisper model. Returns the response
    object; callers read .segments for per-sentence timestamps+text, or .text
    for the single joined transcript."""
    with open(file_path, "rb") as f:
        resp = client().audio.transcriptions.create(
            file=f,
            model=settings.groq_whisper_model,
            language=language,
            response_format="verbose_json",
        )
    return resp
