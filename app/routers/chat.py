from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, ChatMessage, LibraryWord
from app.schemas import ChatIn, ChatOut
from app.auth import get_current_user
from app import llm_client

router = APIRouter(prefix="/chat", tags=["chat"])

PARTNER_SYSTEM_TEMPLATE = (
    "You are a friendly Mandarin Chinese conversation partner chatting with a learner, often about a video "
    "they just watched. Speak ONLY in Mandarin Chinese characters — no pinyin, no English, anywhere in your "
    "reply. Keep your vocabulary and sentence complexity adapted to a learner who currently knows about "
    "{level} words (keep it very simple if that number is low). Never correct the learner's grammar or "
    "word choice — just continue the conversation naturally, the way a patient native speaker friend would. "
    "Only ask what they meant if their message is genuinely unintelligible."
)

TUTOR_SYSTEM = (
    "You are a warm, precise Mandarin Chinese tutor. The learner asks questions in English about how to say "
    "things, or what words/phrases mean. Answer in English, include Chinese characters and pinyin when "
    "relevant, and keep answers concise."
)


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.channel not in ("partner", "tutor"):
        raise HTTPException(400, "channel must be 'partner' or 'tutor'")

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id, ChatMessage.channel == body.channel)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    db.add(ChatMessage(user_id=user.id, channel=body.channel, role="user", text=body.message))
    db.flush()

    convo = "\n".join(f"{'Learner' if m.role == 'user' else 'You'}: {m.text}" for m in history)
    convo += f"\nLearner: {body.message}"

    if body.channel == "partner":
        level = db.query(LibraryWord).filter(LibraryWord.user_id == user.id).count()
        system = PARTNER_SYSTEM_TEMPLATE.format(level=level)
        reply = llm_client.call(system, convo, max_tokens=400).strip()
    else:
        reply = llm_client.call(TUTOR_SYSTEM, convo, max_tokens=500).strip()

    db.add(ChatMessage(user_id=user.id, channel=body.channel, role="assistant", text=reply))
    db.commit()
    return ChatOut(reply=reply)


@router.get("/{channel}")
def history(channel: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id, ChatMessage.channel == channel)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [{"role": m.role, "text": m.text} for m in msgs]
