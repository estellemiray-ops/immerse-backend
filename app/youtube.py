import re
import tempfile
import os
from typing import List, Tuple

from youtube_transcript_api import YouTubeTranscriptApi

from app import llm_client


def extract_video_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    m = re.search(r"(?:youtu\.be/|v=|embed/)([A-Za-z0-9_-]{11})", url_or_id)
    if m:
        return m.group(1)
    if len(url_or_id) == 11:
        return url_or_id
    raise ValueError("Could not find a YouTube video id in that input.")


def fetch_captions(video_id: str) -> Tuple[List[str], str]:
    """
    Only trust captions the creator actually uploaded — YouTube's own
    auto-generated captions (and anything auto-translated into Chinese) are
    frequently wrong on tones, word boundaries, and homophones, which would
    poison every lesson built on top of them. If no manually-created Chinese
    transcript exists, we return nothing here and the caller falls back to
    Whisper, which we trust more than YouTube's auto-captions.
    Returns (list_of_text_lines, source_label) or ([], "") if none exist.
    Any failure here (blocked IP, no captions, network) just means "no captions":
    the Whisper fallback gets a turn.
    """
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
    except Exception:
        return [], ""

    candidates = ["zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW"]
    for code in candidates:
        try:
            t = transcript_list.find_manually_created_transcript([code])
            data = t.fetch().to_raw_data()
            lines = [seg["text"].replace("\n", " ").strip() for seg in data if seg["text"].strip()]
            if lines:
                return lines, "youtube_captions"
        except Exception:
            continue

    return [], ""


def _download_audio(video_id: str, tmp_dir: str) -> str:
    import yt_dlp

    audio_path = os.path.join(tmp_dir, "audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_path,
        "quiet": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        msg = str(e)
        lowered = msg.lower()
        if "not a bot" in lowered or "sign in to confirm" in lowered:
            raise RuntimeError(
                "YouTube is refusing to let this server download the video's audio "
                "(it blocks many cloud hosts as 'bots'). The video itself is fine."
            )
        if "private" in lowered or "unavailable" in lowered:
            raise RuntimeError("That video is private or unavailable.")
        raise RuntimeError(f"Could not download this video's audio: {msg[:300]}")

    mp3_path = os.path.join(tmp_dir, "audio.mp3")
    if os.path.exists(mp3_path):
        return mp3_path
    files = [f for f in os.listdir(tmp_dir) if f.startswith("audio")]
    if not files:
        raise RuntimeError("Could not download audio for this video.")
    return os.path.join(tmp_dir, files[0])


def lines_from_whisper(resp) -> List[str]:
    """Turn a Whisper response into subtitle lines (one per segment)."""
    segments = getattr(resp, "segments", None)
    if segments:
        lines = [seg["text"].strip() if isinstance(seg, dict) else seg.text.strip() for seg in segments]
        return [l for l in lines if l]
    # fall back to splitting the joined transcript on sentence punctuation
    text = getattr(resp, "text", "") or ""
    return [l.strip() for l in re.split(r"[。！？\n]", text) if l.strip()]


def segments_from_whisper(resp) -> list:
    """Like lines_from_whisper but keeps each segment's start time (seconds into the audio)."""
    out = []
    for seg in getattr(resp, "segments", None) or []:
        if isinstance(seg, dict):
            text, start = seg.get("text", ""), seg.get("start", 0)
        else:
            text, start = getattr(seg, "text", ""), getattr(seg, "start", 0)
        text = (text or "").strip()
        if text:
            out.append({"start": float(start or 0), "text": text})
    return out


def transcribe_with_whisper(video_id: str) -> Tuple[List[str], str]:
    """
    Fallback for videos with no creator-uploaded captions: download audio
    with yt-dlp, transcribe it with Groq's hosted Whisper model (free tier,
    no card, fast). We trust this more than YouTube's own auto-captions.
    Groq caps audio uploads around 25MB (free tier), so very long videos may
    need to be trimmed — this raises a clear error if the file is too large
    rather than silently failing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _download_audio(video_id, tmp)

        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        if size_mb > 24:
            raise RuntimeError(
                f"This video's audio is ~{size_mb:.0f}MB after compression, over Groq's free-tier "
                "25MB upload limit. Try a shorter video for now."
            )

        resp = llm_client.transcribe_audio(audio_path, language="zh")
        return lines_from_whisper(resp), "whisper"


def get_transcript_lines(video_id: str) -> Tuple[List[str], str]:
    lines, source = fetch_captions(video_id)
    if lines:
        return lines, source
    return transcribe_with_whisper(video_id)
