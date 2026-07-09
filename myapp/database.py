from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from myapp.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_database():
    global engine, SessionLocal

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return
    except Exception as exc:
        message = str(exc)
        if "Unknown database" not in message and "1049" not in message:
            raise

        database_name = engine.url.database
        if not database_name:
            raise RuntimeError("Database name is missing in DATABASE_URL")
 
        admin_url = str(engine.url).replace(f"/{database_name}", "/mysql")
        admin_engine = create_engine(admin_url, echo=False)
        try:
            with admin_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database_name}`"))
        finally:
            admin_engine.dispose()

        engine.dispose()
        engine = create_engine(settings.DATABASE_URL, echo=False)
        SessionLocal.configure(bind=engine)


def init_db():
    ensure_database()
    Base.metadata.create_all(bind=engine)
