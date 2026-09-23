"""add_tsvector_update_trigger

Revision ID: 85372ad8127d
Revises: 1cc855a33807
Create Date: 2026-09-23 13:22:35.535397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85372ad8127d'
down_revision: Union[str, Sequence[str], None] = '1cc855a33807'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
