"""Change rating_date to ride_date

Revision ID: 221d81698ffc
Revises: 8714ee60e4c1
Create Date: 2025-12-13 00:19:35.817979

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '221d81698ffc'
down_revision: Union[str, Sequence[str], None] = '8714ee60e4c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('paved_ratings', 'rating_date', new_column_name='ride_date')
    op.alter_column('unpaved_ratings', 'rating_date', new_column_name='ride_date')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('paved_ratings', 'ride_date', new_column_name='rating_date')
    op.alter_column('unpaved_ratings', 'ride_date', new_column_name='rating_date')
