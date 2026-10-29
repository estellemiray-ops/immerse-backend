import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, LibraryWord, CardState
from app.schemas import MarkLearntIn, SaveWordIn, LibraryWordOut, LessonOut
from app.auth import get_current_user
from app.srs import CARD_TYPES
from app import llm_client

router = APIRouter(prefix="/words", tags=["words"])

LESSON_SYSTEM = "You are a Mandarin Chinese teaching assistant giving short, precise mini-lessons."


def _to_out(w: LibraryWord) -> LibraryWordOut:
    return LibraryWordOut(
        zh=w.zh, pinyin=w.pinyin, meaning=w.meaning, status=w.status,
        examples=json.loads(w.examples_json or "[]"), added_at=w.added_at,
    )


@router.get("", response_model=list[LibraryWordOut])
def list_library(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    words = db.query(LibraryWord).filter(LibraryWord.user_id == user.id).order_by(LibraryWord.added_at.desc()).all()
    return [_to_out(w) for w in words]


@router.post("/learnt", response_model=LibraryWordOut)
def mark_learnt(body: MarkLearntIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    existing = db.query(LibraryWord).filter(LibraryWord.user_id == user.id, LibraryWord.zh == body.zh).first()
    if existing:
        return _to_out(existing)  # never downgrade a saved word
    w = LibraryWord(user_id=user.id, zh=body.zh, pinyin=body.pinyin, meaning=body.en, status="learnt")
    db.add(w)
    db.commit()
    db.refresh(w)
    return _to_out(w)


@router.post("/lesson", response_model=LessonOut)
def get_lesson(body: MarkLearntIn):
    user_prompt = (
        f'Give a mini lesson for the Mandarin word/phrase "{body.zh}" '
        f'(rough pinyin "{body.pinyin}", rough gloss "{body.en}"). Return JSON exactly like:\n'
        '{"zh":"...","pinyin":"...","meaning":"short clear English meaning",'
        '"examples":[{"zh":"example sentence 1","pinyin":"...","en":"..."},'
        '{"zh":"example sentence 2","pinyin":"...","en":"..."}]}'
    )
    data = llm_client.call_json(LESSON_SYSTEM, user_prompt, max_tokens=600)
    return LessonOut(**data)


@router.post("/save", response_model=LibraryWordOut)
def save_word(body: SaveWordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    w = db.query(LibraryWord).filter(LibraryWord.user_id == user.id, LibraryWord.zh == body.zh).first()
    if not w:
        w = LibraryWord(user_id=user.id, zh=body.zh)
        db.add(w)
        db.flush()
    w.pinyin = body.pinyin
    w.meaning = body.meaning
    w.examples_json = json.dumps(body.examples)
    w.status = "saved"
    db.flush()

    existing_types = {c.card_type for c in db.query(CardState).filter(CardState.word_id == w.id).all()}
    for t in CARD_TYPES:
        if t not in existing_types:
            db.add(CardState(word_id=w.id, card_type=t))

    db.commit()
    db.refresh(w)
    return _to_out(w)
