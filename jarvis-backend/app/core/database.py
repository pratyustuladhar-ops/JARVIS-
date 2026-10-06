import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

logger = logging.getLogger("jarvis.database")

Base = declarative_base()

def get_engine():
    db_url = settings.DATABASE_URL
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        return create_engine(db_url, connect_args=connect_args)
    else:
        # PostgreSQL engine with resilient connection pool parameters
        try:
            return create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20
            )
        except Exception as e:
            logger.warning(
                f"Failed to create engine for {db_url}: {e}. "
                f"Falling back to local SQLite for development resilience."
            )
            return create_engine(
                "sqlite:///./jarvis_fallback.db",
                connect_args={"check_same_thread": False}
            )

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all tables and seed default mock data if empty."""
    try:
        # Import all models to ensure they register with Base.metadata
        from app.models import user, task, memory, project, activity, chat, cms  # noqa
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Error initializing database tables: {e}")
