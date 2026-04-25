"""Test fixtures — set up an in-memory SQLite DB before any app code imports."""
import os

# Configure before any app.* imports so the engine is built against SQLite.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest

from app.database import init_db
from app.database.session import Base, engine


@pytest.fixture(autouse=True)
def _clean_db():
    """Reset all tables between tests for isolation."""
    Base.metadata.drop_all(engine)
    init_db()
    yield
    Base.metadata.drop_all(engine)
