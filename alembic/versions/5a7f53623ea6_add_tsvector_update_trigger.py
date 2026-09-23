"""add_tsvector_update_trigger

Revision ID: 5a7f53623ea6
Revises: 85372ad8127d
Create Date: 2026-09-23 13:34:27.504859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a7f53623ea6'
down_revision: Union[str, Sequence[str], None] = '85372ad8127d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE OR REPLACE FUNCTION update_conversation_search_vector() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := 
            setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') || 
            setweight(to_tsvector('english', coalesce(NEW.customer_name, '')), 'B') || 
            setweight(to_tsvector('english', coalesce(NEW.customer_identifier, '')), 'B');
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trg_conversation_search_vector
        BEFORE INSERT OR UPDATE OF summary, customer_name, customer_identifier
        ON conversations
        FOR EACH ROW
        EXECUTE FUNCTION update_conversation_search_vector();
    """)
    
    op.execute("UPDATE conversations SET updated_at = updated_at;")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_conversation_search_vector ON conversations;")
    op.execute("DROP FUNCTION IF EXISTS update_conversation_search_vector();")
