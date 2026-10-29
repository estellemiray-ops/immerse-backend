from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings
from app.routers import auth, videos, words, review, story, chat, tts, translate, grammar, books, pronounce

Base.metadata.create_all(bind=engine)

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
