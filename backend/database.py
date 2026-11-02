import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

ROOT_DIR = Path(os.environ.get("BUILDCONNECT_PROJECT_ROOT", Path(__file__).resolve().parents[1])).resolve()
DB_PATH = ROOT_DIR / "buildconnect.db"

# Environment variables
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SECRET_KEY = os.environ.get("SECRET_KEY", os.environ.get("BUILDCONNECT_SECRET_KEY", "local-development-key-change-before-deploy"))
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "buildconnect-jwt-secret-key-change-before-deploy")
ACCESS_TOKEN_EXPIRES_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
REFRESH_TOKEN_EXPIRES_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRES_DAYS", "7"))
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", os.environ.get("BUILDCONNECT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")).split(",")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")

Base = declarative_base()

def get_engine():
    """Create SQLAlchemy engine with connection pooling and database type awareness."""
    if DATABASE_URL.startswith(("postgresql://", "postgresql+")):
        return create_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=(FLASK_ENV == "development" and os.environ.get("SQL_DEBUG") == "1"),
        )
    # Default SQLite fallback
    sqlite_url = f"sqlite:///{DB_PATH.as_posix()}"
    return create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        echo=(FLASK_ENV == "development" and os.environ.get("SQL_DEBUG") == "1"),
    )

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
