"""GeoSpacial Coordinates

Revision ID: 8714ee60e4c1
Revises: c67e3d6098e1
Create Date: 2025-10-20 18:22:35.718392

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = '8714ee60e4c1'
down_revision: Union[str, Sequence[str], None] = 'c67e3d6098e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('twists', 'route_geometry')
    op.add_column('twists', sa.Column('route_geometry', geoalchemy2.Geometry(geometry_type='LINESTRING', srid=4326), nullable=False))
    # op.create_index('idx_twists_route_geometry', 'twists', ['route_geometry'], unique=False, postgresql_using='gist')  # Geometry object automatically creates an index


def downgrade() -> None:
    """Downgrade schema."""
    # op.drop_index('idx_twists_route_geometry', table_name='twists', postgresql_using='gist')  # Geometry object automatically creates an index
    op.drop_column('twists', 'route_geometry')
    op.add_column('twists', sa.Column('route_geometry', postgresql.JSONB(astext_type=sa.Text()), nullable=False))
