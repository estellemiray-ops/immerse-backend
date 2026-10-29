import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, LibraryWord, CardState
from app.schemas import ReviewItem, GradeIn, LibraryWordOut
from app.auth import get_current_user
from app.srs import grade as grade_fn, now_ms

router = APIRouter(prefix="/review", tags=["review"])


def _word_out(w: LibraryWord) -> LibraryWordOut:
    return LibraryWordOut(
        zh=w.zh, pinyin=w.pinyin, meaning=w.meaning, status=w.status,
        examples=json.loads(w.examples_json or "[]"), added_at=w.added_at,
    )


@router.get("/queue", response_model=list[ReviewItem])
def queue(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    due_cards = (
        db.query(CardState, LibraryWord)
        .join(LibraryWord, CardState.word_id == LibraryWord.id)
        .filter(LibraryWord.user_id == user.id, LibraryWord.status == "saved", CardState.due_at <= now_ms())
        .all()
    )
    return [ReviewItem(word=w.zh, card_type=c.card_type, entry=_word_out(w)) for c, w in due_cards]


@router.post("/grade")
def grade(body: GradeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    w = db.query(LibraryWord).filter(LibraryWord.user_id == user.id, LibraryWord.zh == body.zh).first()
    if not w:
        raise HTTPException(404, "Word not found.")
    card = db.query(CardState).filter(CardState.word_id == w.id, CardState.card_type == body.card_type).first()
    if not card:
        raise HTTPException(404, "Card not found.")
    ease, interval, reps, due_at = grade_fn(card.ease, card.interval_days, card.reps, body.grade)
    card.ease, card.interval_days, card.reps, card.due_at = ease, interval, reps, due_at
    db.commit()
    return {"ok": True, "next_due_at": due_at}
