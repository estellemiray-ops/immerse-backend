import time
from sqlalchemy import Column, Integer, BigInteger, Boolean, String, Float, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


def now_ms() -> int:
    return int(time.time() * 1000)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(BigInteger, default=now_ms)


class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    youtube_id = Column(String, nullable=False)
    title = Column(String, default="")
    source = Column(String, default="captions")  # captions | whisper
    created_at = Column(BigInteger, default=now_ms)
    # complete: every line has been aligned/translated. transcript: the FULL raw
    # Mandarin lines as a JSON list, saved up front so other features never depend
    # on how far the reader has got.
    complete = Column(Boolean, default=False)
    transcript = Column(Text, default="")

    lines = relationship("Line", back_populates="video", cascade="all, delete-orphan", order_by="Line.order_index")


class Line(Base):
    __tablename__ = "lines"
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    order_index = Column(Integer, nullable=False)
    start_ms = Column(BigInteger, default=0)

    video = relationship("Video", back_populates="lines")
    chunks = relationship("Chunk", back_populates="line", cascade="all, delete-orphan", order_by="Chunk.order_index")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False)
    order_index = Column(Integer, nullable=False)
    zh = Column(String, nullable=False)
    pinyin = Column(String, default="")
    en = Column(String, default="")

    line = relationship("Line", back_populates="chunks")


class LibraryWord(Base):
    __tablename__ = "library_words"
    __table_args__ = (UniqueConstraint("user_id", "zh", name="uq_user_word"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    zh = Column(String, nullable=False)
    pinyin = Column(String, default="")
    meaning = Column(String, default="")
    examples_json = Column(Text, default="[]")
    status = Column(String, default="learnt")  # learnt | saved
    added_at = Column(BigInteger, default=now_ms)

    cards = relationship("CardState", back_populates="word", cascade="all, delete-orphan")


CARD_TYPES = ["audio_type", "zh_to_en", "pronounce", "en_to_zh"]


class CardState(Base):
    __tablename__ = "card_states"
    __table_args__ = (UniqueConstraint("word_id", "card_type", name="uq_word_cardtype"),)
    id = Column(Integer, primary_key=True)
    word_id = Column(Integer, ForeignKey("library_words.id"), nullable=False)
    card_type = Column(String, nullable=False)
    ease = Column(Float, default=2.5)
    interval_days = Column(Float, default=0)
    reps = Column(Integer, default=0)
    due_at = Column(BigInteger, default=now_ms)

    word = relationship("LibraryWord", back_populates="cards")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel = Column(String, nullable=False)  # partner | tutor
    role = Column(String, nullable=False)  # user | assistant
    text = Column(Text, nullable=False)
    created_at = Column(BigInteger, default=now_ms)
