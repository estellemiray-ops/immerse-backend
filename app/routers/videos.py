from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import User, Video, Line, Chunk
from app.schemas import ProcessVideoIn, VideoOut
from app.auth import get_current_user
from app import youtube, llm_client

router = APIRouter(prefix="/videos", tags=["videos"])

ALIGN_SYSTEM = (
    "You segment and translate Mandarin subtitle lines for a language-learning app. "
    "You break each line into short aligned word/phrase chunks between Chinese and English so a "
    "learner can tap either language and see the same aligned term."
)


def align_batch(raw_lines: list[str]) -> list[dict]:
    user = (
        "For each numbered Mandarin line below, return one JSON object with a `chunks` array of "
        '{"zh": "...", "pinyin": "...", "en": "..."} covering the whole line in order. '
        "Return a JSON array, one object per line, same order as input.\n\n"
        + "\n".join(f"{i + 1}. {l}" for i, l in enumerate(raw_lines))
    )
    result = llm_client.call_json(ALIGN_SYSTEM, user, max_tokens=1400)
    return result if isinstance(result, list) else []


@router.post("", response_model=VideoOut)
def process_video(body: ProcessVideoIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        video_id = youtube.extract_video_id(body.youtube_url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    existing = (
        db.query(Video)
        .options(joinedload(Video.lines).joinedload(Line.chunks))
        .filter(Video.user_id == user.id, Video.youtube_id == video_id)
        .first()
    )
    if existing:
        return existing

    try:
        raw_lines, source = youtube.get_transcript_lines(video_id)
    except Exception as e:
        raise HTTPException(422, f"Couldn't get a transcript for this video: {e}")

    if not raw_lines:
        raise HTTPException(422, "No speech or captions could be found for this video.")

    video = Video(user_id=user.id, youtube_id=video_id, source=source)
    db.add(video)
    db.flush()

    batch_size = 6
    order_index = 0
    for i in range(0, len(raw_lines), batch_size):
        batch = raw_lines[i : i + batch_size]
        aligned = align_batch(batch)
        for line_data in aligned:
            chunks = line_data.get("chunks") or []
            if not chunks:
                continue
            line = Line(video_id=video.id, order_index=order_index)
            db.add(line)
            db.flush()
            for c_idx, c in enumerate(chunks):
                db.add(
                    Chunk(
                        line_id=line.id,
                        order_index=c_idx,
                        zh=c.get("zh", ""),
                        pinyin=c.get("pinyin", ""),
                        en=c.get("en", ""),
                    )
                )
            order_index += 1

    db.commit()
    db.refresh(video)
    return video


@router.get("", response_model=list[VideoOut])
def list_videos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Video)
        .options(joinedload(Video.lines).joinedload(Line.chunks))
        .filter(Video.user_id == user.id)
        .order_by(Video.created_at.desc())
        .all()
    )


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = (
        db.query(Video)
        .options(joinedload(Video.lines).joinedload(Line.chunks))
        .filter(Video.id == video_id, Video.user_id == user.id)
        .first()
    )
    if not video:
        raise HTTPException(404, "Video not found.")
    return video
