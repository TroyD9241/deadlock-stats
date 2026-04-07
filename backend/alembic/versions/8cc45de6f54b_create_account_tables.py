"""create account tables

Revision ID: 8cc45de6f54b
Revises: 9cd7d1ecab0e
Create Date: 2026-04-07 13:35:08.241466

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8cc45de6f54b"
down_revision: Union[str, Sequence[str], None] = "9cd7d1ecab0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default="false"),
        sa.Column("steam_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("account_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "players",
        sa.Column("steam_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("rank_tier", sa.Integer(), nullable=True),
        sa.Column("opted_out", sa.Boolean(), server_default="false"),
        sa.Column("tracked_since", sa.DateTime(), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("steam_id"),
    )

    op.create_table(
        "player_name_history",
        sa.Column("steam_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("steam_id", "display_name"),
    )

    op.create_table(
        "account_follows",
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("steam_id", sa.BigInteger(), nullable=False),
        sa.Column("followed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("account_id", "steam_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
