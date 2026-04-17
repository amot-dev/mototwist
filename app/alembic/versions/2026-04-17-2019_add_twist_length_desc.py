"""Add Twist length/desc

Revision ID: e79cd2cc6cb8
Revises: dc9544f838d9
Create Date: 2026-04-17 20:19:27.983332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e79cd2cc6cb8'
down_revision: Union[str, Sequence[str], None] = 'dc9544f838d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('twists', sa.Column('length_m', sa.Float(), sa.Computed('ST_Length(route_geometry::geography)', persisted=True), nullable=False))
    op.add_column('twists', sa.Column('description', sa.String(), server_default='', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('twists', 'description')
    op.drop_column('twists', 'length_m')
