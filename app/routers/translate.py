from fastapi import APIRouter, Depends

from app.schemas import TranslateIn, TranslateOut
from app.auth import get_current_user
from app.models import User
from app import llm_client

router = APIRouter(prefix="/translate", tags=["translate"])

TRANSLATE_SYSTEM = (
    "You translate English into natural, everyday spoken Mandarin Chinese for a language learner, "
    "then break the Mandarin translation into short aligned word/phrase chunks so the learner can tap "
    "individual words and look them up."
)


@router.post("", response_model=TranslateOut)
def translate(body: TranslateIn, user: User = Depends(get_current_user)):
    user_prompt = (
        f'Translate this into natural spoken Mandarin: "{body.text}"\n'
        'Return JSON: {"chunks":[{"zh":"...","pinyin":"...","en":"aligned English gloss for this chunk"}, ...]} '
        "covering the whole translated sentence in order."
    )
    data = llm_client.call_json(TRANSLATE_SYSTEM, user_prompt, max_tokens=500)
    return TranslateOut(translation_chunks=data.get("chunks", []))
