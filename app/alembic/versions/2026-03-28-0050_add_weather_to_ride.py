"""Add Weather to Ride

Revision ID: dc9544f838d9
Revises: 21fe8e7a856b
Create Date: 2026-03-28 00:50:45.175940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc9544f838d9'
down_revision: Union[str, Sequence[str], None] = '21fe8e7a856b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add enums
    temperature = sa.Enum('FREEZING', 'COLD', 'NEUTRAL', 'WARM', 'HOT', name='weather_temperature')
    light_level = sa.Enum('DAY', 'NIGHT', 'TWILIGHT', name='weather_light_level')
    weather_type = sa.Enum('SUNNY', 'CLOUDY', 'RAINY', 'SNOWY', 'HAILING', name='weather_type')
    intensity = sa.Enum('NONE', 'LIGHT', 'MEDIUM', 'HEAVY', name='weather_intensity')
    temperature.create(op.get_bind())
    light_level.create(op.get_bind())
    weather_type.create(op.get_bind())
    intensity.create(op.get_bind())

    # Add columns
    op.add_column('rides', sa.Column(
        'weather_light',
        light_level,
        nullable=False, server_default='DAY'
    ))
    op.add_column('rides', sa.Column(
        'weather_type',
        weather_type,
        nullable=False, server_default='SUNNY'
    ))
    op.add_column('rides', sa.Column(
        'weather_precipitation',
        intensity,
        nullable=False, server_default='NONE'
    ))
    op.add_column('rides', sa.Column(
        'weather_wind',
        intensity,
        nullable=False, server_default='NONE'
    ))
    op.add_column('rides', sa.Column(
        'weather_fog',
        intensity,
        nullable=False, server_default='NONE'
    ))
    op.add_column('rides', sa.Column(
        'weather_temperature',
        temperature,
        nullable=False, server_default='NEUTRAL'
    ))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop columns
    op.drop_column('rides', 'weather_fog')
    op.drop_column('rides', 'weather_wind')
    op.drop_column('rides', 'weather_precipitation')
    op.drop_column('rides', 'weather_sky')
    op.drop_column('rides', 'weather_light')
    op.drop_column('rides', 'weather_temperature')

    # Drop enums
    sa.Enum(name='weather_temperature').drop(op.get_bind())
    sa.Enum(name='weather_light_level').drop(op.get_bind())
    sa.Enum(name='weather_type').drop(op.get_bind())
    sa.Enum(name='weather_intensity').drop(op.get_bind())
