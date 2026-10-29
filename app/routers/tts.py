from fastapi import APIRouter, Query
from fastapi.responses import Response

from app import tts

router = APIRouter(prefix="/tts", tags=["tts"])


@router.get("")
async def speak(text: str = Query(..., max_length=200)):
    audio = await tts.synthesize(text)
    return Response(content=audio, media_type="audio/mpeg")
