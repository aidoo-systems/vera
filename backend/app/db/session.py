from __future__ import annotations

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_SQLITE_PATH = os.getenv("SQLITE_PATH", "./data/vera.db")
os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)
DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
