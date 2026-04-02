"""
SQLAlchemy ORM models.
All models use async-compatible declarative base.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Channel(Base):
    """A tracked YouTube channel."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    input_url: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    videos: Mapped[List["Video"]] = relationship(
        "Video", back_populates="channel", cascade="all, delete-orphan"
    )
    detections: Mapped[List["Detection"]] = relationship(
        "Detection", back_populates="channel", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Channel id={self.id} title={self.channel_title!r} active={self.is_active}>"


class Video(Base):
    """A video fetched from YouTube."""

    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("youtube_video_id", name="uq_video_yt_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    youtube_video_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_short: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    video_url: Mapped[str] = mapped_column(String(256), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="videos")
    detections: Mapped[List["Detection"]] = relationship(
        "Detection", back_populates="video", cascade="all, delete-orphan"
    )

    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"

    def __repr__(self) -> str:
        return f"<Video id={self.id} yt_id={self.youtube_video_id!r} views={self.view_count}>"


class Detection(Base):
    """A record of an anomaly detected for a video."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_percent: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_method: Mapped[str] = mapped_column(String(32), nullable=False)
    view_count_at_detection: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sent_to_chat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="detected", nullable=False
    )  # detected | sent | failed

    video: Mapped["Video"] = relationship("Video", back_populates="detections")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="detections")

    def __repr__(self) -> str:
        return (
            f"<Detection id={self.id} video_id={self.video_id} "
            f"ratio={self.anomaly_ratio:.2f} sent={self.sent_to_chat}>"
        )


class Setting(Base):
    """Key-value store for runtime settings."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r} value={self.value!r}>"


class Admin(Base):
    """Telegram admins who can manage the bot."""

    __tablename__ = "admins"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Admin tg_id={self.telegram_user_id} username={self.username!r}>"
