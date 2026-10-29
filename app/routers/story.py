from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, LibraryWord
from app.schemas import StoryOut
from app.auth import get_current_user
from app import llm_client

router = APIRouter(prefix="/story", tags=["story"])

STORY_SYSTEM = "You write short graded Mandarin reading passages for language learners."


@router.post("/generate", response_model=StoryOut)
def generate_story(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    words = [w.zh for w in db.query(LibraryWord).filter(LibraryWord.user_id == user.id).all()]
    known = "、".join(words) if words else "(none yet — use very basic HSK1 words)"
    user_prompt = (
        f"Write a short simple Mandarin story (6-10 short sentences) that reuses as many of these known "
        f"words as natural: {known}. Include a few new useful words beyond that list, marked isNew. Return JSON:\n"
        '{"title":"...","lines":[{"chunks":[{"zh":"...","pinyin":"...","en":"...","isNew":true|false}]}]}'
    )
    data = llm_client.call_json(STORY_SYSTEM, user_prompt, max_tokens=1400)
    return StoryOut(title=data.get("title", ""), lines=data.get("lines", []))
