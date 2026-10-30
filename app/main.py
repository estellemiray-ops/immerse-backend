from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings
from app.routers import auth, videos, words, review, story, chat, tts, translate, grammar, books, pronounce

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


_widen_timestamp_columns()

app = FastAPI(title="Immerse API")

origins = ["*"] if settings.cors_origins.strip() == "*" else [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/health")
def health():
    return {"status": "ok"}
