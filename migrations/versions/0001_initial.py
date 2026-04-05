"""Initial schema — all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-02 09:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- channels ---
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("youtube_channel_id", sa.String(length=64), nullable=False),
        sa.Column("channel_title", sa.String(length=255), nullable=False),
        sa.Column("input_url", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_channel_id"),
    )

    # --- videos ---
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("youtube_video_id", sa.String(length=64), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("is_short", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("video_url", sa.String(length=256), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_video_id", name="uq_video_yt_id"),
    )
    op.create_index("ix_videos_channel_id", "videos", ["channel_id"])
    op.create_index("ix_videos_published_at", "videos", ["published_at"])

    # --- detections ---
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("anomaly_ratio", sa.Float(), nullable=False),
        sa.Column("anomaly_percent", sa.Float(), nullable=False),
        sa.Column("baseline_method", sa.String(length=32), nullable=False),
        sa.Column("view_count_at_detection", sa.BigInteger(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_to_chat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="detected"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detections_video_id", "detections", ["video_id"])
    op.create_index("ix_detections_sent", "detections", ["sent_to_chat"])

    # --- settings ---
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    # --- admins ---
    op.create_table(
        "admins",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )


def downgrade() -> None:
    op.drop_table("admins")
    op.drop_table("settings")
    op.drop_index("ix_detections_sent", table_name="detections")
    op.drop_index("ix_detections_video_id", table_name="detections")
    op.drop_table("detections")
    op.drop_index("ix_videos_published_at", table_name="videos")
    op.drop_index("ix_videos_channel_id", table_name="videos")
    op.drop_table("videos")
    op.drop_table("channels")
