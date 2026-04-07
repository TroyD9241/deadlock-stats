"""create_match_tables

Revision ID: a1b2c3d4e5f6
Revises: 8cc45de6f54b
Create Date: 2026-04-07 13:35:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8cc45de6f54b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("duration_secs", sa.Integer(), nullable=True),
        sa.Column("match_mode", sa.String(50), nullable=True),
        sa.Column("winning_team", sa.Integer(), nullable=True),
        sa.Column("patch_version", sa.String(20), nullable=True),
        sa.Column("average_rank", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), server_default="deadlock_api"),
        sa.PrimaryKeyConstraint("match_id"),
    )
    op.create_table(
        "match_players",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("steam_id", sa.Integer(), nullable=False),
        sa.Column("team", sa.Integer(), nullable=False),
        sa.Column("hero_id", sa.Integer(), nullable=True),
        sa.Column("kills", sa.Integer(), server_default="0"),
        sa.Column("deaths", sa.Integer(), server_default="0"),
        sa.Column("assists", sa.Integer(), server_default="0"),
        sa.Column("net_worth", sa.Integer(), server_default="0"),
        sa.Column("last_hits", sa.Integer(), server_default="0"),
        sa.Column("denies", sa.Integer(), server_default="0"),
        sa.Column("damage_dealt", sa.Integer(), server_default="0"),
        sa.Column("damage_taken", sa.Integer(), server_default="0"),
        sa.Column("healing_done", sa.Integer(), server_default="0"),
        sa.Column("creep_kills", sa.Integer(), server_default="0"),
        sa.Column("tower_kills", sa.Integer(), server_default="0"),
        sa.Column("mvp", sa.Boolean(), server_default="0"),
        sa.Column("ranked_badge_level", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.match_id"]),
        sa.ForeignKeyConstraint(["steam_id"], ["players.steam_id"]),
        sa.ForeignKeyConstraint(["hero_id"], ["heroes.hero_id"]),
        sa.PrimaryKeyConstraint("match_id", "steam_id"),
    )


def downgrade() -> None:
    op.drop_table("match_players")
    op.drop_table("matches")
