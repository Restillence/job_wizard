import os
import pytest
from sqlalchemy import text
from src.database import engine

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="Live DB test. Set RUN_LIVE_TESTS=1 to run.",
)


def test_database_connection() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
