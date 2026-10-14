import redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from myapp.core.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
)


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def configure_sqlite_transactions(target):
    if target.dialect.name != "sqlite":
        return

    @event.listens_for(target, "connect")
    def connect(conn, _):
        conn.isolation_level = None
        conn.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(target, "begin")
    def begin(conn):
        conn.exec_driver_sql("BEGIN")


configure_sqlite_transactions(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


def init_db():
    # Fresh installations only. Existing schemas require `alembic upgrade head`.
    Base.metadata.create_all(bind=engine)
