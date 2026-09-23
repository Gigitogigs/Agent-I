"""Add CHECK constraints for documents and chunks

Revision ID: 9a1da8b16ff3
Revises: df5dcd741a2e
Create Date: 2026-09-23 12:20:56.361366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1da8b16ff3'
down_revision: Union[str, Sequence[str], None] = 'df5dcd741a2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint('chk_doc_file_size_positive', 'documents', 'file_size_bytes >= 0')
    op.create_check_constraint('chk_chunk_idx_positive', 'document_chunks', 'chunk_index >= 0', schema='rag')
    op.create_check_constraint('chk_token_count_positive', 'document_chunks', 'token_count >= 0', schema='rag')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('chk_token_count_positive', 'document_chunks', type_='check', schema='rag')
    op.drop_constraint('chk_chunk_idx_positive', 'document_chunks', type_='check', schema='rag')
    op.drop_constraint('chk_doc_file_size_positive', 'documents', type_='check')
