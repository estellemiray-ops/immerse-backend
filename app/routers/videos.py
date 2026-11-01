import base64
import binascii
import json
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import User, Video, Line, Chunk
from app.schemas import ProcessVideoIn, VideoOut, LinesChunkIn, LinesChunkOut, TranscriptOut
from app.auth import get_current_user
from app import youtube, llm_client

router = APIRouter(prefix="/videos", tags=["videos"])

ALIGN_SYSTEM = (
    "You segment and translate Mandarin subtitle lines for a language-learning app. "
    "You break each line into short aligned word/phrase chunks between Chinese and English so a "
    "learner can tap either language and see the same aligned term."
)


CONTEXT_LINES = 4


def summarize_video(transcript: list[str]) -> str:
    """One short summary so every batch knows what the video is about."""
    try:
        text = "\n".join(transcript)[:3500]
        return llm_client.call(
            "You summarize Mandarin video transcripts for a translator.",
            "In at most 2 short English sentences, say what this video is about, who is speaking, "
            "and the tone.\n\n" + text,
            max_tokens=150,
        ).strip()
    except Exception:
        return ""


def align_batch(raw_lines, before=None, after=None, summary="", ref_en=None) -> list[dict]:
    parts = []
    if summary:
        parts.append(f"About the whole video: {summary}\n")
    if before:
        parts.append("Context only (lines just BEFORE; do not translate):\n" + "\n".join(before) + "\n")
    parts.append(
        "Translate ONLY the numbered lines below. Subtitle lines are often fragments of a longer "
        "sentence, so use the surrounding lines to get the meaning right, and translate each chunk "
        "by what it means in this sentence, not as a dictionary entry. "
        'For each numbered line return one JSON object with a `chunks` array of '
        '{"zh": "...", "pinyin": "...", "en": "..."} covering the whole line in order, '
        "in natural English that reads smoothly line to line. Return a JSON array, one object per line, same order as input.\n"
    )
    lines_txt = []
    for i, l in enumerate(raw_lines):
        row = f"{i + 1}. {l}"
        if ref_en and i < len(ref_en) and ref_en[i]:
            row += f"   [official English subtitle: {ref_en[i]}]"
        lines_txt.append(row)
    parts.append("\n".join(lines_txt))
    if after:
        parts.append("\nContext only (lines just AFTER; do not translate):\n" + "\n".join(after))
    result = llm_client.call_json(ALIGN_SYSTEM, "\n".join(parts), max_tokens=1600)
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

    video = Video(user_id=user.id, youtube_id=video_id, source=source, transcript=json.dumps(raw_lines))
    db.add(video)
    db.flush()
    _store_aligned(db, video, _align_all(raw_lines, summary=summarize_video(raw_lines)), 0)
    video.complete = True
    db.commit()
    db.refresh(video)
    return video


def _align_all(raw_lines, transcript=None, base=0, summary="", ref_en=None, batch_size=5) -> list[dict]:
    """transcript = the whole video's lines (for context); base = where raw_lines starts in it."""
    transcript = transcript or raw_lines
    out: list[dict] = []
    for i in range(0, len(raw_lines), batch_size):
        batch = raw_lines[i : i + batch_size]
        g = base + i
        before = transcript[max(0, g - CONTEXT_LINES) : g]
        after = transcript[g + len(batch) : g + len(batch) + CONTEXT_LINES]
        refs = ref_en[i : i + batch_size] if ref_en else None
        aligned = align_batch(batch, before, after, summary, refs)
        aligned = (aligned + [{}] * len(batch))[: len(batch)]
        out.extend(aligned)
    return out


def _store_aligned(db: Session, video: Video, aligned: list[dict], start_order: int) -> list[Line]:
    """Save aligned lines; order_index is the raw line's position in the whole transcript."""
    saved = []
    for i, line_data in enumerate(aligned):
        chunks = (line_data or {}).get("chunks") or []
        if not chunks:
            continue
        line = Line(video_id=video.id, order_index=start_order + i)
        db.add(line)
        db.flush()
        for c_idx, c in enumerate(chunks):
            db.add(Chunk(line_id=line.id, order_index=c_idx, zh=c.get("zh", ""), pinyin=c.get("pinyin", ""), en=c.get("en", "")))
        saved.append(line)
    return saved


def _delete_lines(db: Session, video_id: int, from_order: int) -> None:
    """Delete lines (and their chunks) at or after from_order. Bulk deletes skip ORM
    cascades, so remove the chunks first."""
    ids = [r[0] for r in db.query(Line.id).filter(Line.video_id == video_id, Line.order_index >= from_order).all()]
    if ids:
        db.query(Chunk).filter(Chunk.line_id.in_(ids)).delete(synchronize_session=False)
        db.query(Line).filter(Line.id.in_(ids)).delete(synchronize_session=False)
    db.flush()


class AudioB64In(BaseModel):
    audio_b64: str
    ext: str = "webm"


def _whisper_bytes(data: bytes, suffix: str) -> list[str]:
    if not data:
        raise HTTPException(400, "The audio file was empty.")
    if len(data) > 24 * 1024 * 1024:
        raise HTTPException(413, "That audio is over Groq's 25MB free limit.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        resp = llm_client.transcribe_audio(path, language="zh")
    finally:
        os.remove(path)
    return youtube.lines_from_whisper(resp)


@router.post("/transcribe-b64")
def transcribe_b64(body: AudioB64In, user: User = Depends(get_current_user)):
    """Audio pieces recorded by the in-app player arrive as base64 text. A piece with no
    speech (music, silence) simply returns no lines."""
    try:
        data = base64.b64decode(body.audio_b64, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "That audio wasn't valid.")
    ext = "".join(ch for ch in body.ext if ch.isalnum())[:5] or "webm"
    return {"lines": _whisper_bytes(data, "." + ext)}


@router.post("/transcribe")
async def transcribe_uploaded_audio(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """For videos with no usable Chinese captions: the phone downloads the audio itself
    (YouTube blocks this server) and uploads it here for Groq's Whisper."""
    data = await audio.read()
    if len(data) > 24 * 1024 * 1024:
        raise HTTPException(413, "That audio is over Groq's 25MB free limit — try a shorter video.")
    if not data:
        raise HTTPException(400, "The audio file was empty.")
    suffix = os.path.splitext(audio.filename or "audio.m4a")[1] or ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        resp = llm_client.transcribe_audio(path, language="zh")
    finally:
        os.remove(path)
    lines = youtube.lines_from_whisper(resp)
    if not lines:
        raise HTTPException(422, "Whisper couldn't hear any speech in that audio.")
    return {"lines": lines}


@router.post("/chunk", response_model=LinesChunkOut)
def receive_chunk(body: LinesChunkIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The phone fetches captions itself (YouTube blocks this server) and sends them
    in small batches. The FULL transcript is stored at offset 0, so it exists on the
    server immediately; the batches only fill in the aligned/translated display."""
    if not body.lines or len(body.lines) > 40:
        raise HTTPException(400, "Send between 1 and 40 lines per request.")

    video = db.query(Video).filter(Video.user_id == user.id, Video.youtube_id == body.youtube_id).first()

    if body.offset == 0:
        if video and video.complete:
            full = (
                db.query(Video)
                .options(joinedload(Video.lines).joinedload(Line.chunks))
                .filter(Video.id == video.id)
                .first()
            )
            return LinesChunkOut(video_id=video.id, cached=True, lines=full.lines)
        if video:  # unfinished earlier attempt: start clean
            _delete_lines(db, video.id, 0)
        else:
            video = Video(user_id=user.id, youtube_id=body.youtube_id)
            db.add(video)
        video.source = body.source
        video.complete = False
        video.transcript = json.dumps(body.full_transcript or body.lines)
        db.flush()
    elif not video:
        raise HTTPException(409, "Start from the beginning of the video first.")
    else:
        # a retried batch replaces anything already saved at or after its offset
        _delete_lines(db, video.id, body.offset)

    try:
        transcript = json.loads(video.transcript or "[]")
    except ValueError:
        transcript = []
    summary = body.summary or ""
    if body.offset == 0 and not summary:
        summary = summarize_video(transcript or body.lines)
    aligned = _align_all(body.lines, transcript or None, body.offset, summary, body.ref_en)
    saved = _store_aligned(db, video, aligned, body.offset)
    if body.final:
        video.complete = True
    db.commit()
    for l in saved:
        db.refresh(l)
    return LinesChunkOut(video_id=video.id, cached=False, summary=summary, lines=saved)


@router.get("/{video_id}/transcript", response_model=TranscriptOut)
def get_transcript(video_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == user.id).first()
    if not video:
        raise HTTPException(404, "Video not found.")
    try:
        lines = json.loads(video.transcript or "[]")
    except ValueError:
        lines = []
    return TranscriptOut(video_id=video.id, youtube_id=video.youtube_id, complete=bool(video.complete), source=video.source, lines=lines)


@router.get("", response_model=list[VideoOut])
def list_videos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Video)
        .options(joinedload(Video.lines).joinedload(Line.chunks))
        .filter(Video.user_id == user.id)
        .order_by(Video.created_at.desc())
        .all()
    )


@router.get("/by-youtube/{youtube_id}", response_model=VideoOut)
def get_by_youtube_id(youtube_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Returns the finished video for this YouTube id, so reopening it skips all the work."""
    video = (
        db.query(Video)
        .options(joinedload(Video.lines).joinedload(Line.chunks))
        .filter(Video.user_id == user.id, Video.youtube_id == youtube_id, Video.complete == True)  # noqa: E712
        .first()
    )
    if not video:
        raise HTTPException(404, "Not processed yet.")
    return video


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
