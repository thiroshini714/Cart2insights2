"""Database connectivity. Credentials come from environment variables / .env only."""
from __future__ import annotations

import os
from urllib.parse import quote_plus

from .config import ROOT


def build_database_url() -> str:
    """Return a SQLAlchemy URL built from the environment (never hardcoded)."""
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit

    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    if backend == "mysql":
        missing = [k for k in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
        if missing:
            raise RuntimeError(
                f"DB_BACKEND=mysql but these variables are not set: {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in."
            )
        user = quote_plus(os.environ["DB_USER"])
        password = quote_plus(os.environ["DB_PASSWORD"])
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{os.environ['DB_NAME']}"

    if backend != "sqlite":
        raise RuntimeError(f"Unsupported DB_BACKEND '{backend}'. Use 'sqlite' or 'mysql'.")
    path = os.getenv("SQLITE_PATH", "data/cart2insights.db")
    path = path if os.path.isabs(path) else str(ROOT / path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite:///{path}"


def get_engine():
    """Create a SQLAlchemy engine (SQLite gets foreign-key enforcement switched on)."""
    from sqlalchemy import create_engine, event

    url = build_database_url()
    engine = create_engine(url, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def create_mysql_database_if_missing() -> None:
    """Create the MySQL database named in DB_NAME if it does not exist yet."""
    if os.getenv("DB_BACKEND", "sqlite").lower() != "mysql" or os.getenv("DATABASE_URL"):
        return
    from sqlalchemy import create_engine, text

    user = quote_plus(os.environ["DB_USER"])
    password = quote_plus(os.environ["DB_PASSWORD"])
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    name = os.environ["DB_NAME"]
    if not name.replace("_", "").isalnum():
        raise RuntimeError("DB_NAME may only contain letters, digits and underscores.")
    server = create_engine(f"mysql+pymysql://{user}:{password}@{host}:{port}/")
    with server.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{name}`"))
