from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.models import User
from app import llm_client

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post("/check")
def check_key(user: User = Depends(get_current_user)):
    """Checks the Groq key sent in the X-Groq-Key header with one tiny request."""
    if not llm_client.user_key.get():
        raise HTTPException(400, "No key was sent.")
    llm_client.client().models.list()  # a bad key raises an auth error, handled in main.py
    return {"ok": True}
