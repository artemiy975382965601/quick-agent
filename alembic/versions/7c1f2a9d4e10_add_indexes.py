"""add indexes

Revision ID: 7c1f2a9d4e10
Revises: 492074bc0aa3
Create Date: 2026-11-18 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c1f2a9d4e10'
down_revision: Union[str, Sequence[str], None] = '492074bc0aa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_pinned_files_session_inject_content',
        'pinned_files',
        ['session_id', 'type_of_inject', 'type_of_content'],
        unique=False,
    )
    op.create_index(
        'ix_pinned_files_session_file',
        'pinned_files',
        ['session_id', 'file'],
        unique=True,
    )
    op.create_index(
        'ix_messages_session_id_id',
        'messages',
        ['session_id', 'id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_messages_session_id_id', table_name='messages')
    op.drop_index('ix_pinned_files_session_file', table_name='pinned_files')
    op.drop_index('ix_pinned_files_session_inject_content', table_name='pinned_files')
