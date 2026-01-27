"""Add frequency_class

Revision ID: 72fa6239962f
Revises: d2c4d583d806
Create Date: 2026-01-27 16:49:05.679089

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72fa6239962f'
down_revision: Union[str, Sequence[str], None] = 'd2c4d583d806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the Enum type first
    op.execute("CREATE TYPE frequencyclass AS ENUM ('A', 'B', 'C')")
    op.add_column('product_definitions', sa.Column('frequency_class', sa.Enum('A', 'B', 'C', name='frequencyclass'), nullable=True))
    
    # Update existing records to default 'C'
    op.execute("UPDATE product_definitions SET frequency_class = 'C'")
    
    # Make it non-nullable now that we have data
    op.alter_column('product_definitions', 'frequency_class', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('product_definitions', 'frequency_class')
    op.execute("DROP TYPE frequencyclass")
