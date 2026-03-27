"""Switch from Paved/Unpaved Ratings to Rides

Revision ID: 21fe8e7a856b
Revises: 049492e2c1d6
Create Date: 2026-03-27 20:45:22.048993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '21fe8e7a856b'
down_revision: Union[str, Sequence[str], None] = '049492e2c1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new tables
    op.execute("CREATE SEQUENCE criteria_sort_order_seq")
    op.create_table('criteria',
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text("nextval('criteria_sort_order_seq')"), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('for_paved', sa.Boolean(), nullable=False),
        sa.Column('for_unpaved', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('slug')
    )

    op.create_table('rides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('twist_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('ratings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['twist_id'], ['twists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Migrate Data from paved_ratings
    op.execute("""
        INSERT INTO rides (author_id, twist_id, date, ratings)
        SELECT
            author_id,
            twist_id,
            ride_date,
            jsonb_build_object(
                'seclusion', seclusion,
                'scenery', scenery,
                'pavement', pavement,
                'twistyness', twistyness,
                'intensity', intensity
            )
        FROM paved_ratings;
    """)

    # Migrate Data from unpaved_ratings
    op.execute("""
        INSERT INTO rides (author_id, twist_id, date, ratings)
        SELECT
            author_id,
            twist_id,
            ride_date,
            jsonb_build_object(
                'seclusion', seclusion,
                'scenery', scenery,
                'surface_consistency', surface_consistency,
                'technicality', technicality,
                'flow', flow
            )
        FROM unpaved_ratings;
    """)

    # Drop old tables and unneeded index
    op.drop_table('paved_ratings')
    op.drop_table('unpaved_ratings')
    op.drop_index(op.f('ix_twists_id'), table_name='twists')


def downgrade() -> None:
    # Recreate old tables
    op.create_table('paved_ratings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('twist_id', sa.Integer(), nullable=False),
        sa.Column('ride_date', sa.Date(), nullable=False),
        sa.Column('seclusion', sa.SmallInteger(), nullable=False),
        sa.Column('scenery', sa.SmallInteger(), nullable=False),
        sa.Column('pavement', sa.SmallInteger(), nullable=False),
        sa.Column('twistyness', sa.SmallInteger(), nullable=False),
        sa.Column('intensity', sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['twist_id'], ['twists.id'], ondelete='CASCADE')
    )

    op.create_table('unpaved_ratings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('twist_id', sa.Integer(), nullable=False),
        sa.Column('ride_date', sa.Date(), nullable=False),
        sa.Column('seclusion', sa.SmallInteger(), nullable=False),
        sa.Column('scenery', sa.SmallInteger(), nullable=False),
        sa.Column('surface_consistency', sa.SmallInteger(), nullable=False),
        sa.Column('technicality', sa.SmallInteger(), nullable=False),
        sa.Column('flow', sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['twist_id'], ['twists.id'], ondelete='CASCADE')
    )

    # Migrate data back to paved_ratings (non-null check on pavement to ensure these are paved)
    op.execute("""
        INSERT INTO paved_ratings (author_id, twist_id, ride_date, seclusion, scenery, pavement, twistyness, intensity)
        SELECT
            author_id,
            twist_id,
            date,
            (ratings->>'seclusion')::smallint,
            (ratings->>'scenery')::smallint,
            (ratings->>'pavement')::smallint,
            (ratings->>'twistyness')::smallint,
            (ratings->>'intensity')::smallint
        FROM rides
        WHERE ratings->>'pavement' IS NOT NULL;
    """)

    # 3. Migrate data back to unpaved_ratings (non-null check on surface_consistency to ensure these are unpaved)
    op.execute("""
        INSERT INTO unpaved_ratings (author_id, twist_id, ride_date, seclusion, scenery, surface_consistency, technicality, flow)
        SELECT
            author_id,
            twist_id,
            date,
            (ratings->>'seclusion')::smallint,
            (ratings->>'scenery')::smallint,
            (ratings->>'surface_consistency')::smallint,
            (ratings->>'technicality')::smallint,
            (ratings->>'flow')::smallint
        FROM rides
        WHERE ratings->>'surface_consistency' IS NOT NULL;
    """)

    # Drop new tables and restore index
    op.drop_table('rides')
    op.drop_table('criteria')
    op.execute("DROP SEQUENCE criteria_sort_order_seq")
    op.create_index(op.f('ix_twists_id'), 'twists', ['id'], unique=False)
