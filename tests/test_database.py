from sqlalchemy import text
from src.database import engine


def test_database_connection() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
