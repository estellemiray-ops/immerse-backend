from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import groq
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings
from app import llm_client
from app.routers import keys, auth, videos, words, review, story, chat, tts, translate, grammar, books, pronounce

Base.metadata.create_all(bind=engine)


def _widen_timestamp_columns():
    """Tables created by an earlier version used 32-bit INTEGER for millisecond
    timestamps, which overflow on Postgres. create_all() never alters existing
    tables, so convert those columns to BIGINT. Safe to run on every startup:
    converting a BIGINT column to BIGINT is a no-op."""
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE users ALTER COLUMN created_at TYPE BIGINT",
        "ALTER TABLE videos ALTER COLUMN created_at TYPE BIGINT",
        "ALTER TABLE lines ALTER COLUMN start_ms TYPE BIGINT",
        "ALTER TABLE library_words ALTER COLUMN added_at TYPE BIGINT",
        "ALTER TABLE card_states ALTER COLUMN due_at TYPE BIGINT",
        "ALTER TABLE chat_messages ALTER COLUMN created_at TYPE BIGINT",
    ]
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:  # never block startup over a migration hiccup
            print(f"[migrate] skipped ({e.__class__.__name__}): {stmt}")


def _add_video_columns():
    if engine.dialect.name != "postgresql":
        return
    for stmt in [
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS complete BOOLEAN DEFAULT FALSE",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS transcript TEXT DEFAULT ''",
    ]:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:
            print(f"[migrate] skipped ({e.__class__.__name__}): {stmt}")


_widen_timestamp_columns()
_add_video_columns()

app = FastAPI(title="Immerse API")

origins = ["*"] if settings.cors_origins.strip() == "*" else [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(keys.router)
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(words.router)
app.include_router(review.router)
app.include_router(story.router)
app.include_router(chat.router)
app.include_router(tts.router)
app.include_router(translate.router)
app.include_router(grammar.router)
app.include_router(books.router)
app.include_router(pronounce.router)


@app.middleware("http")
async def groq_key_from_header(request: Request, call_next):
    llm_client.user_key.set(request.headers.get("x-groq-key", "").strip())
    return await call_next(request)


def _json(status: int, msg: str):
    # built by hand so CORS headers still get added by the middleware
    return JSONResponse(status_code=status, content={"detail": msg})


@app.exception_handler(llm_client.NoKeyError)
async def _no_key(request: Request, exc):
    return _json(400, str(exc))


@app.exception_handler(groq.AuthenticationError)
async def _bad_key(request: Request, exc):
    return _json(400, "Groq didn't accept that key. Check it in Tools → AI key.")


@app.exception_handler(groq.APIStatusError)
async def _groq_status(request: Request, exc):
    detail = ""
    try:
        detail = (exc.body or {}).get("error", {}).get("message", "") if isinstance(exc.body, dict) else ""
    except Exception:
        pass
    return _json(502, f"Groq answered with an error ({exc.status_code}): {detail or exc.message}")


@app.exception_handler(groq.APIConnectionError)
async def _groq_conn(request: Request, exc):
    return _json(502, "Couldn't reach Groq from the server. Try again in a moment.")


@app.exception_handler(groq.RateLimitError)
async def _rate(request: Request, exc):
    return _json(429, "Groq's free limit was reached for now. Wait a minute or two and try again.")


@app.get("/health")
def health():
    return {"status": "ok"}
