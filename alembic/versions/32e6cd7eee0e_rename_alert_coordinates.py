"""rename_alert_coordinates

Revision ID: 32e6cd7eee0e
Revises: 9396d1f01911
Create Date: 2026-01-09 09:01:33.406735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32e6cd7eee0e'
down_revision: Union[str, Sequence[str], None] = '9396d1f01911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('alerts', 'x', new_column_name='position_row')
    op.alter_column('alerts', 'y', new_column_name='position_col')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('alerts', 'position_row', new_column_name='x')
    op.alter_column('alerts', 'position_col', new_column_name='y')
