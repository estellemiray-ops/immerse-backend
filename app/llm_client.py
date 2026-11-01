import json
import re
import time
from contextvars import ContextVar
from groq import Groq, RateLimitError, NotFoundError, BadRequestError
from app.config import settings

_client = None
# The Groq key the person typed into the app, for the request being handled.
# Set per request by a middleware in main.py; falls back to the server's own key.
user_key: ContextVar[str] = ContextVar("user_key", default="")


class NoKeyError(Exception):
    pass


def client() -> Groq:
    global _client
    key = user_key.get()
    if key:
        return Groq(api_key=key)
    if not settings.groq_api_key:
        raise NoKeyError("Add your free Groq key in Tools → AI key to use this.")
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


_working_model = ""  # remembered once a model has answered, so we don't re-probe every call


def _model_chain() -> list[str]:
    chain = [m.strip() for m in [settings.groq_model] + settings.groq_fallback_models.split(",") if m.strip()]
    if _working_model and _working_model in chain:
        chain.remove(_working_model)
        chain.insert(0, _working_model)
    return chain


def _extra_for(model: str) -> dict:
    # "no reasoning" means different things per model family
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    return {"reasoning_effort": "none"}


def _create_with_retry(messages, max_tokens):
    """Calls Groq, waiting out free-tier rate limits (429) and moving to the next model if
    Groq has retired the current one (404)."""
    global _working_model
    last_missing = None
    for model in _model_chain():
        extra = _extra_for(model)
        tokens = max_tokens + (1200 if model.startswith("openai/gpt-oss") else 0)  # reasoning counts as output
        for attempt in range(4):
            try:
                resp = client().chat.completions.create(
                    model=model, max_tokens=tokens, messages=messages, extra_body=extra
                )
                _working_model = model
                return resp
            except RateLimitError:
                if attempt == 3:
                    raise
                time.sleep(min(8 * (attempt + 1), 25))
            except BadRequestError as e:
                # a model that doesn't accept our reasoning setting: retry once without it
                if extra and "reasoning" in str(e).lower():
                    extra = {}
                    continue
                raise
            except NotFoundError as e:
                last_missing = e
                break  # this model is gone; try the next one
    if last_missing:
        raise last_missing
    raise RuntimeError("No Groq model is configured.")


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def call(system: str, user: str, max_tokens: int = 1000) -> str:
    resp = _create_with_retry(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens,
    )
    return _THINK.sub("", resp.choices[0].message.content or "").strip()


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
