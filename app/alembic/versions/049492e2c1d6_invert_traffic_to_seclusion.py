"""Invert traffic to seclusion

Revision ID: 049492e2c1d6
Revises: 221d81698ffc
Create Date: 2026-03-27 00:42:20.164361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '049492e2c1d6'
down_revision: Union[str, Sequence[str], None] = '221d81698ffc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Max value as of this migration
CRITERION_MAX_VALUE = 10


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('paved_ratings', 'traffic', new_column_name='seclusion')
    op.alter_column('unpaved_ratings', 'traffic', new_column_name='seclusion')
    for table_name in ['paved_ratings', 'unpaved_ratings']:
        t = sa.sql.table(table_name, sa.sql.column('seclusion', sa.Integer))
        op.execute(
            t.update().values(seclusion=CRITERION_MAX_VALUE - t.c.seclusion)
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table_name in ['paved_ratings', 'unpaved_ratings']:
        t = sa.sql.table(table_name, sa.sql.column('seclusion', sa.Integer))
        op.execute(
            t.update().values(seclusion=CRITERION_MAX_VALUE - t.c.seclusion)
        )
    op.alter_column('paved_ratings', 'seclusion', new_column_name='traffic')
    op.alter_column('unpaved_ratings', 'seclusion', new_column_name='traffic')
