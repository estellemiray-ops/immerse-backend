from fastapi import APIRouter, Depends

from app.schemas import GrammarCheckIn, GrammarCheckOut
from app.auth import get_current_user
from app.models import User
from app import llm_client

router = APIRouter(prefix="/grammar", tags=["grammar"])

GRAMMAR_SYSTEM = (
    "You are a precise Mandarin Chinese grammar checker for a language learner. Unlike a casual "
    "conversation partner, your job here IS to correct mistakes — word order, particles (了/的/地/得), "
    "measure words, aspect markers, etc. Be clear and specific but not harsh."
)


@router.post("/check", response_model=GrammarCheckOut)
def check(body: GrammarCheckIn, user: User = Depends(get_current_user)):
    user_prompt = (
        f'The learner wrote this Mandarin sentence: "{body.text}"\n'
        "Return JSON: {\"is_correct\": true|false, \"corrected\": \"the corrected sentence (same as input if "
        'already correct)", "explanation": "a short, specific, encouraging explanation of what was wrong and '
        'why, in English — or a brief note of praise if it was already correct"}'
    )
    data = llm_client.call_json(GRAMMAR_SYSTEM, user_prompt, max_tokens=400)
    return GrammarCheckOut(**data)
