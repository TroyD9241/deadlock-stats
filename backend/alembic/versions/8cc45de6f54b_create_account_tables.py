"""create account tables

Revision ID: 8cc45de6f54b
Revises: 9cd7d1ecab0e
Create Date: 2026-04-07 13:35:08.241466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8cc45de6f54b'
down_revision: Union[str, Sequence[str], None] = '9cd7d1ecab0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
