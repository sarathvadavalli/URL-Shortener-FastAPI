from alembic import context
from sqlalchemy import create_engine

from myapp.core.config import settings
from myapp.database import Base
from myapp.models import url_mapping, user_model  # noqa: F401


def run_migrations():
    if context.is_offline_mode():
        raise RuntimeError(
            "Online migration required for duplicate preflight and backfill"
        )
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
