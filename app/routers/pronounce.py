import tempfile
import os
from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.auth import get_current_user
from app.models import User
from app import llm_client

router = APIRouter(prefix="/pronounce", tags=["pronounce"])


@router.post("/check")
async def check(
    audio: UploadFile = File(...),
    expected_zh: str = Form(...),
    user: User = Depends(get_current_user),
):
    suffix = os.path.splitext(audio.filename or "recording.m4a")[1] or ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name
    try:
        resp = llm_client.transcribe_audio(tmp_path, language="zh")
        heard = (getattr(resp, "text", "") or "").strip()
    finally:
        os.remove(tmp_path)

    # simple exact-ish match after stripping punctuation/whitespace; the
    # learner can always see what was actually heard and self-grade, so this
    # is a helpful signal rather than the sole judge
    normalize = lambda s: "".join(ch for ch in s if ch.isalnum())
    is_match = normalize(heard) == normalize(expected_zh)

    return {"heard": heard, "expected": expected_zh, "is_match": is_match}
