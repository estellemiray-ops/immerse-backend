from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, LibraryWord
from app.schemas import BookRecommendationsOut
from app.auth import get_current_user
from app import llm_client

router = APIRouter(prefix="/books", tags=["books"])

BOOKS_SYSTEM = (
    "You are a well-read Mandarin Chinese reading tutor who recommends real, genuinely existing books "
    "(graded readers, children's books, or full novels depending on level) appropriate to a learner's "
    "current vocabulary size. Never invent books — only recommend ones you're confident really exist."
)

MIN_WORDS_FOR_RECOMMENDATIONS = 30


@router.get("/recommendations", response_model=BookRecommendationsOut)
def recommendations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    words = db.query(LibraryWord).filter(LibraryWord.user_id == user.id).all()
    if len(words) < MIN_WORDS_FOR_RECOMMENDATIONS:
        raise HTTPException(
            400,
            f"Save at least {MIN_WORDS_FOR_RECOMMENDATIONS} words before asking for book recommendations "
            f"(currently {len(words)}) — recommendations before that tend to be too advanced to be useful.",
        )
    sample = "、".join(w.zh for w in words[:80])
    user_prompt = (
        f"A Mandarin learner knows about {len(words)} words, including: {sample}. "
        "Based on this vocabulary size, recommend 3 real books suited to their current level (mix of "
        "difficulty is fine — one comfortable, one stretch). Return JSON: "
        '{"level_summary": "one sentence on their rough level", "books": '
        '[{"title":"...", "author":"...", "why":"why it fits this level, one sentence"}]}'
    )
    data = llm_client.call_json(BOOKS_SYSTEM, user_prompt, max_tokens=600)
    return BookRecommendationsOut(**data)
