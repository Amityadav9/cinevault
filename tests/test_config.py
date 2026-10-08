from app.core.config import Settings


def test_database_url_uses_psycopg3_driver():
    s = Settings(postgres_user="u", postgres_password="p", postgres_host="h", postgres_db="d")
    assert s.database_url == "postgresql+psycopg://u:p@h:5435/d"
