"""create reference tables

Revision ID: 9cd7d1ecab0e
Revises:
Create Date: 2026-04-07 13:32:26.299508

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9cd7d1ecab0e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "heroes",
        sa.Column("hero_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("hero_id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "items",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("item_id"),
    )

    op.create_table(
        "abilities",
        sa.Column("ability_id", sa.Integer(), nullable=False),
        sa.Column("hero_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("ability_id"),
        sa.ForeignKeyConstraint(["hero_id"], ["heroes.hero_id"]),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("abilities")
    op.drop_table("items")
    op.drop_table("heroes")
