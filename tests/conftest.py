import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.models import Base
from app.core.database import Database
from config.settings import settings


@pytest.fixture(scope="function")
def test_db():
    """Создаёт временную in-memory базу для тестов"""
    # Используем sqlite в памяти — быстро и изолировано
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = Database()  # но мы подменим engine
    db.engine = engine
    db.SessionLocal = SessionLocal

    yield db

    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(test_db):
    """Фикстура сессии БД"""
    session = test_db.SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()