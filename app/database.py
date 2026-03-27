import asyncio

from alembic import command
from alembic.config import Config
from socket import socket
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from time import sleep

from app.config import logger
from app.models import Base
from app.settings import settings


engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


async def get_db():
    """
    Dependency to get a database session.
    """
    async with SessionLocal() as session:
        yield session


def create_automigration(message: str):
    """
    Create a new Alembic automigration file based on model changes.
    """
    logger.info(f"Creating automigration with message: '{message}'...")

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option('sqlalchemy.url', settings.SQLALCHEMY_DATABASE_URL)
    alembic_cfg.attributes['target_metadata'] = Base.metadata

    command.revision(alembic_cfg, message=message, autogenerate=True)


async def is_fresh_db() -> bool:
    """
    Check if the db has any tables. If not, immediately build schema directly from models.
    """
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URL)

    async with engine.begin() as connection:
        # Inspection requires a sync connection context
        def get_tables(sync_connection: Connection) -> list[str]:
            return inspect(sync_connection).get_table_names()

        existing_tables = await connection.run_sync(get_tables)

        if not existing_tables:
            logger.info("Fresh database detected. Building schema from models...")
            # Build the schema directly from models
            await connection.run_sync(Base.metadata.create_all)
            return True

        return False


def apply_migrations():
    """
    Migrate the database to the latest version.

    If this is a fresh database, this is done without going through every single migration.
    """
    logger.info("Checking database state for migrations...")

    # Configure alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option('sqlalchemy.url', settings.SQLALCHEMY_DATABASE_URL)
    alembic_cfg.attributes['target_metadata'] = Base.metadata

    # Check if the database is completely empty
    if asyncio.run(is_fresh_db()):
        # Tell Alembic that this database is fully up to date
        logger.info("Stamping Alembic version to 'head'...")
        command.stamp(alembic_cfg, "head")
    else:
        # Standard upgrade path for existing users
        logger.info("Existing database detected. Running Alembic upgrades...")
        command.upgrade(alembic_cfg, "head")


def wait_for_db():
    """
    Wait for the database to be available.
    """
    while True:
        s = socket()
        s.settimeout(2)
        if s.connect_ex((settings.POSTGRES_HOST, settings.POSTGRES_PORT)) == 0:
            logger.info(f"Database is up at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
            s.close()
            break
        logger.info(f"Database unavailable at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}. Sleeping 1s")
        sleep(1)
