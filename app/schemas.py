from typing import List, Optional
from pydantic import BaseModel, EmailStr


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProcessVideoIn(BaseModel):
    youtube_url: str


class ChunkOut(BaseModel):
    zh: str
    pinyin: str = ""
    en: str = ""

    class Config:
        from_attributes = True


class LineOut(BaseModel):
    chunks: List[ChunkOut]
    start_ms: int = 0  # when the line first appears in the video (0 = unknown)

    class Config:
        from_attributes = True


class VideoOut(BaseModel):
    id: int
    youtube_id: str
    title: str
    source: str
    lines: List[LineOut]

    class Config:
        from_attributes = True


class LinesChunkIn(BaseModel):
    youtube_id: str
    source: str = "captions"
    offset: int = 0            # index of the first raw line in `lines`
    lines: List[str]           # 1-40 raw Mandarin lines
    final: bool = False        # true on the last batch
    full_transcript: Optional[List[str]] = None  # send on offset 0: every raw line
    starts: Optional[List[int]] = None  # start time in ms for each line in `lines`
    ref_en: Optional[List[str]] = None  # creator's English for each line in `lines`, if any
    summary: Optional[str] = None       # video summary returned by the first batch


class LinesChunkOut(BaseModel):
    video_id: int
    cached: bool = False
    summary: str = ""
    lines: List[LineOut]


class TranscriptOut(BaseModel):
    video_id: int
    youtube_id: str
    complete: bool
    source: str
    lines: List[str]


class MarkLearntIn(BaseModel):
    zh: str
    pinyin: str = ""
    en: str = ""


class SaveWordIn(BaseModel):
    zh: str
    pinyin: str
    meaning: str
    examples: List[dict] = []


class LibraryWordOut(BaseModel):
    zh: str
    pinyin: str
    meaning: str
    status: str
    examples: list = []
    added_at: int

    class Config:
        from_attributes = True


class LessonOut(BaseModel):
    zh: str
    pinyin: str
    meaning: str
    examples: List[dict]


class ReviewItem(BaseModel):
    word: str
    card_type: str
    entry: LibraryWordOut


class GradeIn(BaseModel):
    zh: str
    card_type: str
    grade: str  # again | hard | good | easy


class StoryOut(BaseModel):
    title: str
    lines: List[dict]


class ChatIn(BaseModel):
    channel: str  # partner | tutor
    message: str


class ChatOut(BaseModel):
    reply: str


class TranslateIn(BaseModel):
    text: str  # what the learner typed in English


class TranslateOut(BaseModel):
    translation_chunks: List[ChunkOut]  # tappable, same shape as subtitle chunks


class GrammarCheckIn(BaseModel):
    text: str  # a sentence the learner wrote in Mandarin


class GrammarCheckOut(BaseModel):
    is_correct: bool
    corrected: str
    explanation: str


class BookRecommendation(BaseModel):
    title: str
    author: str
    why: str


class BookRecommendationsOut(BaseModel):
    level_summary: str
    books: List[BookRecommendation]
